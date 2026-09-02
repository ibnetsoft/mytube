import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import {
    driveFileLink,
    ensureStdProjectDriveFolders,
    uploadStdDriveBuffer,
} from '@/lib/stdGoogleDrive'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'
import { parseScriptToVoiceSegments, ScriptVoiceSegment } from '@/lib/stdMultiVoice'
import { getConfiguredElevenLabsKeys } from '@/lib/elevenLabsKeys'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const DEFAULT_ELEVENLABS_VOICE_ID = 'FGY2WhTYpPnrIDTdsKH5'
const DEFAULT_ELEVENLABS_MODEL_ID = 'eleven_multilingual_v2'
const FALLBACK_ELEVENLABS_MODEL_IDS = ['eleven_v3', 'eleven_multilingual_v2']
const MAX_CHARS_PER_REQUEST = 4500
const MAX_INLINE_AUDIO_BYTES = 2_500_000
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

type ElevenLabsKeyCandidate = {
    apiKey: string
    keySlot: number
    remaining: number | null
    tier?: string | null
    skipped?: boolean
    reason?: string
}

function cleanTtsText(value: string) {
    return String(value || '')
        .replace(/\r\n/g, '\n')
        .replace(/[ \t]+/g, ' ')
        .replace(/\n{3,}/g, '\n\n')
        .trim()
}

function splitText(text: string, maxChars = MAX_CHARS_PER_REQUEST) {
    const cleaned = cleanTtsText(text)
    if (!cleaned) return []

    const paragraphs = cleaned.split(/\n+/).map(part => part.trim()).filter(Boolean)
    const chunks: string[] = []
    let current = ''

    for (const paragraph of paragraphs) {
        if ((current + '\n' + paragraph).trim().length <= maxChars) {
            current = (current ? `${current}\n` : '') + paragraph
            continue
        }
        if (current) chunks.push(current)

        if (paragraph.length <= maxChars) {
            current = paragraph
            continue
        }

        const sentences = paragraph.split(/(?<=[.!?。！？…])\s+/).filter(Boolean)
        current = ''
        for (const sentence of sentences) {
            if ((current + ' ' + sentence).trim().length <= maxChars) {
                current = (current ? `${current} ` : '') + sentence
            } else {
                if (current) chunks.push(current)
                if (sentence.length <= maxChars) {
                    current = sentence
                } else {
                    for (let i = 0; i < sentence.length; i += maxChars) {
                        chunks.push(sentence.slice(i, i + maxChars))
                    }
                    current = ''
                }
            }
        }
    }
    if (current) chunks.push(current)
    return chunks
}

function shouldRotateElevenLabsKey(status: number, detail: string) {
    const message = String(detail || '').toLowerCase()
    if (status === 402) return true
    return (
        message.includes('insufficient balance')
        || message.includes('insufficient credits')
        || message.includes('credit')
        || message.includes('quota')
        || message.includes('billing')
        || message.includes('payment required')
        || message.includes('invalid api key')
        || message.includes('unauthorized')
        || message.includes('access denied')
    )
}

function isElevenLabsVoiceAccessError(status: number, detail: string) {
    if (![400, 401, 403, 404, 422].includes(status)) return false
    const message = String(detail || '').toLowerCase()
    return (
        message.includes('voice_not_found')
        || message.includes('voice is not available')
        || message.includes('voice_access_denied')
        || message.includes('access to this voice')
        || message.includes('free users')
    )
}

function parseElevenLabsQuotaError(detail: string) {
    const raw = String(detail || '')
    let message = raw
    try {
        const parsed = JSON.parse(raw)
        message = String(parsed?.detail?.message || parsed?.message || raw)
    } catch {}

    const match = message.match(/you have\s+([\d,]+)\s+credits?\s+remaining,\s+while\s+([\d,]+)\s+credits?\s+are required/i)
    if (!match) return null

    const remaining = Number(match[1].replace(/,/g, ''))
    const required = Number(match[2].replace(/,/g, ''))
    if (!Number.isFinite(remaining) || !Number.isFinite(required)) return null
    return { remaining, required }
}

function shouldRetryElevenLabsWithAlternateModel(status: number, detail: string) {
    if (status !== 400 && status !== 422) return false
    const message = String(detail || '').toLowerCase()
    return (
        message.includes('model')
        || message.includes('does not support')
        || message.includes('unsupported')
        || message.includes('not available')
        || message.includes('invalid_request_error')
    )
}

function buildElevenLabsModelCandidates(modelId: string) {
    const candidates = [String(modelId || '').trim(), ...FALLBACK_ELEVENLABS_MODEL_IDS]
    return candidates.filter((value, index) => value && candidates.indexOf(value) === index)
}

async function inspectElevenLabsKey(apiKey: string, keySlot: number): Promise<ElevenLabsKeyCandidate> {
    try {
        const res = await fetch('https://api.elevenlabs.io/v1/user/subscription', {
            headers: {
                'xi-api-key': apiKey,
                Accept: 'application/json',
            },
            cache: 'no-store',
        })
        if (!res.ok) {
            const detail = await res.text().catch(() => '')
            return {
                apiKey,
                keySlot,
                remaining: null,
                skipped: [401, 402, 403].includes(res.status),
                reason: `subscription_check_failed_${res.status}: ${detail.slice(0, 180)}`,
            }
        }
        const data = await res.json().catch(() => ({}))
        const limit = Number(data?.character_limit || 0)
        const used = Number(data?.character_count || 0)
        const remaining = Number.isFinite(limit) && Number.isFinite(used) && limit > 0
            ? Math.max(0, limit - used)
            : null
        return {
            apiKey,
            keySlot,
            remaining,
            tier: data?.tier || null,
        }
    } catch (error: any) {
        return {
            apiKey,
            keySlot,
            remaining: null,
            skipped: false,
            reason: `subscription_check_error: ${error?.message || String(error)}`,
        }
    }
}

async function selectUsableElevenLabsKeys(apiKeys: string[], requiredChunkChars: number) {
    const inspections = await Promise.all(apiKeys.map((apiKey, index) => inspectElevenLabsKey(apiKey, index + 1)))
    const minRequired = Math.max(1, Math.min(MAX_CHARS_PER_REQUEST, requiredChunkChars || MAX_CHARS_PER_REQUEST))
    const candidates = inspections
        .map((item) => {
            if (item.skipped) return item
            if (item.remaining != null && item.remaining < minRequired) {
                return {
                    ...item,
                    skipped: true,
                    reason: `잔여 ${item.remaining.toLocaleString('ko-KR')}자 < 청크 필요 ${minRequired.toLocaleString('ko-KR')}자`,
                }
            }
            return item
        })
    return {
        usableKeys: candidates.filter(item => !item.skipped).map(item => item.apiKey),
        usableSlots: candidates.filter(item => !item.skipped).map(item => item.keySlot),
        inspections: candidates.map(({ apiKey, ...safe }) => safe),
    }
}

async function recordStdTtsFailure(input: {
    requester: any
    project: any
    stage: string
    error: any
    textLength?: number
    chunkCount?: number
    keyInspections?: any[]
}) {
    const userId = String(input.requester?.user?.id || input.requester?.profile?.id || '')
    if (!UUID_RE.test(userId)) return
    try {
        await supabaseAdmin.from('ai_logs').insert({
            user_id: userId,
            task_type: 'std_tts_generate',
            model_id: DEFAULT_ELEVENLABS_MODEL_ID,
            provider: 'elevenlabs',
            status: 'failed',
            prompt_summary: `project=${input.project?.id || '-'} text=${input.textLength || 0} chunks=${input.chunkCount || 0} stage=${input.stage}`,
            error_msg: String(input.error?.message || input.error || 'TTS generation failed').slice(0, 500),
            elapsed_time: 0,
            input_tokens: input.textLength || 0,
            output_tokens: 0,
            worker_email: input.requester?.email || null,
        })
    } catch {}
}

async function generateSingleElevenLabsChunk(input: {
    apiKeys: Array<string | ElevenLabsKeyCandidate>
    voiceId: string
    modelId: string
    chunk: string
    speed?: number
    stability?: number
    similarityBoost?: number
    style?: number
}): Promise<{ audioBuffer: Buffer; keySlot: number; modelId: string }> {
    const voiceSettings: Record<string, number> = {}
    if (Number.isFinite(input.stability)) voiceSettings.stability = Number(input.stability)
    if (Number.isFinite(input.similarityBoost)) voiceSettings.similarity_boost = Number(input.similarityBoost)
    if (Number.isFinite(input.style)) voiceSettings.style = Number(input.style)
    if (Number.isFinite(input.speed)) voiceSettings.speed = Math.min(1.2, Math.max(0.7, Number(input.speed)))

    let lastError = 'ElevenLabs API key is not configured'
    const quotaErrors: Array<{ remaining: number; required: number }> = []
    const modelCandidates = buildElevenLabsModelCandidates(input.modelId)
    for (let keyIndex = 0; keyIndex < input.apiKeys.length; keyIndex += 1) {
        const keyCandidate = input.apiKeys[keyIndex]
        const apiKey = typeof keyCandidate === 'string' ? keyCandidate : keyCandidate.apiKey
        const keySlot = typeof keyCandidate === 'string' ? keyIndex + 1 : keyCandidate.keySlot
        for (let modelIndex = 0; modelIndex < modelCandidates.length; modelIndex += 1) {
            const currentModelId = modelCandidates[modelIndex] || DEFAULT_ELEVENLABS_MODEL_ID
            const res = await fetch(
                `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(input.voiceId)}?output_format=mp3_44100_128`,
                {
                    method: 'POST',
                    headers: {
                        'xi-api-key': apiKey,
                        'Content-Type': 'application/json',
                        Accept: 'audio/mpeg',
                    },
                    body: JSON.stringify({
                        text: input.chunk,
                        model_id: currentModelId,
                        voice_settings: Object.keys(voiceSettings).length ? voiceSettings : undefined,
                    }),
                }
            )

            if (res.ok) {
                const arrayBuffer = await res.arrayBuffer()
                const audioBuffer = Buffer.from(arrayBuffer)
                const contentType = String(res.headers.get('content-type') || '').toLowerCase()
                if (audioBuffer.length < 256 || (contentType && !contentType.includes('audio') && !contentType.includes('octet-stream'))) {
                    throw new Error(`ElevenLabs returned an invalid audio response (${audioBuffer.length} bytes, ${contentType || 'unknown type'})`)
                }
                return { audioBuffer, keySlot, modelId: currentModelId }
            }

            const errText = await res.text()
            lastError = `ElevenLabs TTS API error (${res.status}): ${errText}`
            const quotaError = parseElevenLabsQuotaError(errText)
            if (quotaError) quotaErrors.push(quotaError)

            if (isElevenLabsVoiceAccessError(res.status, errText)) {
                lastError = `선택한 성우(${input.voiceId})를 현재 ElevenLabs 키로 사용할 수 없습니다. 등록된 다음 백업 키를 확인합니다.`
                break
            }

            const hasAlternateModel = modelIndex < modelCandidates.length - 1
            if (hasAlternateModel && shouldRetryElevenLabsWithAlternateModel(res.status, errText)) {
                continue
            }

            if (!shouldRotateElevenLabsKey(res.status, errText)) {
                throw new Error(lastError)
            }
            break
        }
    }

    if (quotaErrors.length) {
        const totalRemaining = quotaErrors.reduce((sum, item) => sum + item.remaining, 0)
        const required = Math.max(...quotaErrors.map((item) => item.required))
        throw new Error(
            `ElevenLabs 크레딧이 부족합니다. 등록된 키 ${input.apiKeys.length}개 중 확인된 총 잔여 크레딧은 ${totalRemaining.toLocaleString('ko-KR')}이고, 현재 음성 청크 생성에는 ${required.toLocaleString('ko-KR')}크레딧이 필요합니다. 관리자 페이지에서 키를 충전하거나 잔여 크레딧이 충분한 백업 키를 추가해 주세요.`
        )
    }

    throw new Error(lastError)
}

async function generateElevenLabsMp3(input: {
    apiKeys: Array<string | ElevenLabsKeyCandidate>
    voiceId: string
    modelId: string
    text: string
    speed?: number
    stability?: number
    similarityBoost?: number
    style?: number
    multiVoice?: boolean
    voiceMap?: Record<string, string>
}) {
    const usedKeySlots = new Set<number>()
    const usedModelIds = new Set<string>()

    const rememberChunk = (result: { audioBuffer: Buffer; keySlot: number; modelId: string }) => {
        usedKeySlots.add(result.keySlot)
        usedModelIds.add(result.modelId)
        return result.audioBuffer
    }

    // 1. 멀티 보이스 모드인 경우
    if (input.multiVoice && input.voiceMap && Object.keys(input.voiceMap).length > 0) {
        const { segments } = parseScriptToVoiceSegments(input.text)
        if (!segments.length) throw new Error('TTS multi-voice text has no segments')

        const buffers: Buffer[] = []
        for (const seg of segments) {
            const targetVoiceId = input.voiceMap[seg.speaker] || input.voiceId || DEFAULT_ELEVENLABS_VOICE_ID
            const chunks = splitText(seg.text)
            for (const chunk of chunks) {
                const result = await generateSingleElevenLabsChunk({
                    apiKeys: input.apiKeys,
                    voiceId: targetVoiceId,
                    modelId: input.modelId,
                    chunk,
                    speed: input.speed,
                    stability: input.stability,
                    similarityBoost: input.similarityBoost,
                    style: input.style,
                })
                buffers.push(rememberChunk(result))
            }
        }
        return {
            audioBuffer: Buffer.concat(buffers),
            keySlots: Array.from(usedKeySlots).sort((a, b) => a - b),
            modelIds: Array.from(usedModelIds),
        }
    }

    // 2. 단일 보이스 모드
    const chunks = splitText(input.text)
    if (!chunks.length) throw new Error('TTS text is empty')

    const buffers: Buffer[] = []
    for (const chunk of chunks) {
        const result = await generateSingleElevenLabsChunk({
            apiKeys: input.apiKeys,
            voiceId: input.voiceId,
            modelId: input.modelId,
            chunk,
            speed: input.speed,
            stability: input.stability,
            similarityBoost: input.similarityBoost,
            style: input.style,
        })
        buffers.push(rememberChunk(result))
    }

    return {
        audioBuffer: Buffer.concat(buffers),
        keySlots: Array.from(usedKeySlots).sort((a, b) => a - b),
        modelIds: Array.from(usedModelIds),
    }
}

async function generateSingleGoogleTranslateChunk(chunk: string, lang: string = 'ko'): Promise<Buffer> {
    const normalizedLang = String(lang || 'ko').trim().toLowerCase()
    const tl = normalizedLang.startsWith('ja') || normalizedLang.startsWith('jp')
        ? 'ja'
        : normalizedLang.startsWith('en')
        ? 'en'
        : 'ko'

    const url = new URL('https://translate.google.com/translate_tts')
    url.searchParams.set('ie', 'UTF-8')
    url.searchParams.set('client', 'tw-ob')
    url.searchParams.set('tl', tl)
    url.searchParams.set('q', chunk)

    const res = await fetch(url.toString(), {
        headers: {
            'User-Agent': 'Mozilla/5.0 AIR Studio TTS',
            Accept: 'audio/mpeg,*/*',
        },
    })
    if (!res.ok) {
        const errText = await res.text().catch(() => '')
        throw new Error(`Google free TTS error (${res.status}): ${errText.slice(0, 200)}`)
    }

    return Buffer.from(await res.arrayBuffer())
}

async function generateGoogleFreeMp3(text: string, lang: string = 'ko') {
    const chunks = splitText(text, 180)
    if (!chunks.length) throw new Error('TTS text is empty')

    const buffers: Buffer[] = []
    for (const chunk of chunks) {
        buffers.push(await generateSingleGoogleTranslateChunk(chunk, lang))
    }
    return Buffer.concat(buffers)
}

function buildTtsText(project: any, scenes: any[], overrideText?: string) {
    const raw = String(
        overrideText
        || project.project_payload?.script
        || project.project_payload?.longform_script
        || ''
    ).trim()
    if (raw) return raw

    const parts = (scenes || [])
        .map((scene: any) => String(scene.script_excerpt || scene.scene_text || scene.prompt_ko || '').trim())
        .filter(Boolean)
    return parts.join('\n\n').trim()
}

function topicIdFromProjectParam(projectId: string): number | null {
    const value = String(projectId || '').trim()
    const match = value.match(/^(?:proj-)?(\d+)$/i)
    if (match) return Number(match[1])
    return null
}

async function loadStdProject(projectId: string, employeeEmail: string) {
    const topicQueueId = topicIdFromProjectParam(projectId)

    // 1. Try finding in std_projects for this employee
    let query = supabaseAdmin.from('std_projects').select('*')
    if (UUID_RE.test(projectId)) {
        query = query.eq('id', projectId)
    } else if (topicQueueId != null && Number.isFinite(topicQueueId)) {
        query = query.eq('topic_queue_id', topicQueueId)
    } else {
        return { data: null, error: null }
    }

    const userRes = await query.eq('employee_email', employeeEmail).maybeSingle()
    if (userRes.data) return userRes

    // 2. Try finding in std_projects for any employee (e.g. admin testing)
    let anyQuery = supabaseAdmin.from('std_projects').select('*')
    if (UUID_RE.test(projectId)) {
        anyQuery = anyQuery.eq('id', projectId)
    } else if (topicQueueId != null && Number.isFinite(topicQueueId)) {
        anyQuery = anyQuery.eq('topic_queue_id', topicQueueId)
    }
    const anyRes = await anyQuery.maybeSingle()
    if (anyRes.data) return anyRes

    // 3. Auto-provision project from topics_queue if not yet in std_projects table
    if (topicQueueId != null && Number.isFinite(topicQueueId)) {
        const { data: topicRow } = await supabaseAdmin
            .from('topics_queue')
            .select('*')
            .eq('id', topicQueueId)
            .maybeSingle()

        if (topicRow) {
            const title = topicRow.generated_title || topicRow.topic || '새로운 영상 프로젝트'
            const struct = topicRow.pregenerated_structure || {}
            const scenes = Array.isArray(struct.scenes) ? struct.scenes : []
            const now = new Date().toISOString()

            const insertPayload = {
                topic_queue_id: topicRow.id,
                category_id: topicRow.category_id,
                employee_email: employeeEmail,
                title: title,
                status: 'claimed',
                total_scenes: scenes.length || 53,
                video_scenes: 0,
                image_scenes: scenes.length || 53,
                actual_payout: topicRow.estimated_payout || 10000,
                assigned_duration_minutes: topicRow.assigned_duration_minutes || 15,
                project_payload: {
                    topic_id: topicRow.id,
                    title: title,
                    script: topicRow.pregenerated_script || '',
                    structure: struct,
                    status: 'claimed',
                    tts_speed: topicRow.progress_payload?.tts_speed || 1,
                },
                progress_payload: {
                    status: 'claimed',
                    scenes_count: scenes.length || 53,
                    tts_speed: topicRow.progress_payload?.tts_speed || 1,
                },
                claimed_at: now,
                updated_at: now,
            }

            const { data: createdProject, error: createErr } = await supabaseAdmin
                .from('std_projects')
                .insert(insertPayload)
                .select()
                .single()

            if (createdProject) {
                await supabaseAdmin
                    .from('topics_queue')
                    .update({
                        assigned_employee_email: employeeEmail,
                        status: 'assigned',
                        updated_at: now,
                    })
                    .eq('id', topicRow.id)

                return { data: createdProject, error: null }
            }
        }
    }

    return { data: null, error: null }
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const body = await req.json().catch(() => ({}))

    const { data: project, error: projectError } = await loadStdProject(params.projectId, auth.requester.email)

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const { data: scenesData, error: scenesError } = await supabaseAdmin
        .from('std_project_scenes')
        .select('*')
        .eq('project_id', project.id)
        .order('scene_number', { ascending: true })
    const canIgnoreScenesError = scenesError?.message?.includes('invalid input syntax for type uuid')
    const scenes = canIgnoreScenesError ? [] : (scenesData || [])
    if (scenesError && !canIgnoreScenesError) {
        return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })
    }

    let stage = 'prepare'
    const ttsDebug: {
        textLength: number
        chunkCount: number
        keyInspections: any[]
    } = {
        textLength: 0,
        chunkCount: 0,
        keyInspections: [],
    }
    try {
        stage = 'build_text'
        const text = buildTtsText(project, scenes, body?.text)
        if (!text) return NextResponse.json({ success: false, error: 'TTS text is empty' }, { status: 400 })

        const provider = String(body?.provider || 'elevenlabs').trim()
        const voiceId = String(
            body?.voice_id
            || project.progress_payload?.voice_id
            || project.project_payload?.voice_id
            || DEFAULT_ELEVENLABS_VOICE_ID
        ).trim()
        const modelId = String(body?.model_id || project.project_payload?.tts_model_id || DEFAULT_ELEVENLABS_MODEL_ID).trim()
        const projectTtsSpeed = Math.max(0.7, Math.min(1.2, Number(
            body?.speed
            ?? project.project_payload?.tts_speed
            ?? project.progress_payload?.tts_speed
            ?? project.source_payload?.progress_payload?.tts_speed
            ?? 1
        ) || 1))
        const multiVoice = Boolean(body?.multi_voice)
        const voiceMap = body?.voice_map || {}

        const textChunks = splitText(text)
        const chunkCount = textChunks.length
        const largestChunkChars = textChunks.reduce((max, chunk) => Math.max(max, chunk.length), 0)
        ttsDebug.textLength = text.length
        ttsDebug.chunkCount = chunkCount
        let audioBuffer: Buffer
        let elevenLabsTrace: { keySlots: number[]; modelIds: string[] } | null = null
        let elevenLabsKeyInspections: any[] = []
        if (provider === 'google_free' || voiceId.startsWith('google_')) {
            stage = 'generate_google_free'
            const projectLang = String(
                body?.target_language
                || body?.language
                || project.language
                || project.project_payload?.target_language
                || project.project_payload?.language
                || 'ko'
            ).trim().toLowerCase()
            audioBuffer = await generateGoogleFreeMp3(text, projectLang)
        } else {
            stage = 'load_elevenlabs_key'
            const apiKeys = await getConfiguredElevenLabsKeys()
            if (!apiKeys.length) {
                return NextResponse.json({ success: false, error: 'ElevenLabs API key is not configured' }, { status: 500 })
            }
            const keySelection = await selectUsableElevenLabsKeys(apiKeys, largestChunkChars)
            elevenLabsKeyInspections = keySelection.inspections
            ttsDebug.keyInspections = elevenLabsKeyInspections
            if (!keySelection.usableKeys.length) {
                const totalRemaining = elevenLabsKeyInspections.reduce(
                    (sum, item) => sum + (Number.isFinite(item.remaining) ? Number(item.remaining) : 0),
                    0
                )
                throw new Error(
                    `ElevenLabs 사용 가능한 키가 없습니다. 현재 대본은 ${text.length.toLocaleString('ko-KR')}자, ${chunkCount}개 청크이며 가장 긴 청크는 ${largestChunkChars.toLocaleString('ko-KR')}자입니다. 확인된 총 잔여 크레딧은 ${totalRemaining.toLocaleString('ko-KR')}자입니다.`
                )
            }

            stage = 'generate_elevenlabs'
            const generationResult = await generateElevenLabsMp3({
                apiKeys: keySelection.usableKeys.map((apiKey, index) => ({
                    apiKey,
                    keySlot: keySelection.usableSlots[index],
                    remaining: null,
                })),
                voiceId,
                modelId,
                text,
                speed: projectTtsSpeed,
                stability: body?.stability == null ? undefined : Number(body.stability),
                similarityBoost: body?.similarity_boost == null ? undefined : Number(body.similarity_boost),
                style: body?.style == null ? undefined : Number(body.style),
                multiVoice,
                voiceMap,
            })
            audioBuffer = generationResult.audioBuffer
            elevenLabsTrace = {
                keySlots: generationResult.keySlots,
                modelIds: generationResult.modelIds,
            }
            console.info('[STD TTS] ElevenLabs generation trace', {
                projectId: project.id,
                keySlots: elevenLabsTrace.keySlots,
                modelIds: elevenLabsTrace.modelIds,
                textLength: text.length,
                chunkCount,
                keyPreflight: elevenLabsKeyInspections,
            })
        }

        const now = new Date().toISOString()
        const safeProjectKey = String(project.topic_queue_id || project.id).replace(/[^a-zA-Z0-9_-]/g, '')
        const fileName = `std_tts_${safeProjectKey}_${Date.now()}.mp3`
        stage = 'ensure_drive_folders'
        let folders: any = null
        let driveFile: any = null
        try {
            folders = await ensureStdProjectDriveFolders(project)
            stage = 'upload_drive_file'
            driveFile = await uploadStdDriveBuffer(
                folders.originalsFolderId,
                fileName,
                audioBuffer,
                'audio/mpeg',
                `AIR STD web TTS audio for project ${project.id}`
            )
        } catch (driveError: any) {
            console.error('[STD TTS] Google Drive upload failed; refusing transient-only success:', driveError?.message)
            if (audioBuffer.length <= MAX_INLINE_AUDIO_BYTES) {
                return NextResponse.json({
                    success: true,
                    warning: 'TTS audio was generated, but Google Drive storage failed.',
                    code: 'tts_drive_upload_failed_inline_audio_returned',
                    stage,
                    detail: driveError?.message || null,
                    asset: null,
                    drive_file: null,
                    audio_url: `data:audio/mpeg;base64,${audioBuffer.toString('base64')}`,
                    download_url: '',
                    persisted_audio_url: '',
                    web_view_link: '',
                    elevenlabs_key_slots: elevenLabsTrace?.keySlots || [],
                    elevenlabs_model_ids: elevenLabsTrace?.modelIds || [],
                    message: 'TTS 음성은 생성되었지만 Google Drive 저장은 실패했습니다.',
                })
            }
            return NextResponse.json({
                success: false,
                error: 'TTS audio was generated, but Google Drive storage failed. Please retry.',
                code: 'tts_drive_upload_failed',
                stage,
                detail: driveError?.message || null,
                elevenlabs_key_slots: elevenLabsTrace?.keySlots || [],
                elevenlabs_model_ids: elevenLabsTrace?.modelIds || [],
            }, { status: 502 })
        }

        let asset: any = null
        try {
            stage = 'replace_existing_audio_assets'
            await supabaseAdmin
                .from('std_project_assets')
                .update({ status: 'replaced', updated_at: now })
                .eq('project_id', project.id)
                .eq('asset_type', 'audio')
                .in('status', ['uploaded', 'assigned'])

            stage = 'insert_audio_asset'
            const { data: insertedAsset, error: assetError } = await supabaseAdmin
                .from('std_project_assets')
                .insert({
                    project_id: project.id,
                    scene_id: null,
                    scene_number: null,
                    asset_type: 'audio',
                    drive_file_id: driveFile.id,
                    drive_folder_id: folders.originalsFolderId,
                    file_name: driveFile.name || fileName,
                    mime_type: 'audio/mpeg',
                    file_size: driveFile.size ? Number(driveFile.size) : audioBuffer.length,
                    status: 'uploaded',
                    uploaded_by: auth.requester.user.id,
                    metadata: {
                        provider,
                        voice_id: voiceId,
                        model_id: modelId,
                        tts_speed: projectTtsSpeed,
                        multi_voice: multiVoice,
                        voice_map: voiceMap,
                        text_length: text.length,
                        chunk_count: chunkCount,
                        elevenlabs_key_preflight: elevenLabsKeyInspections,
                        elevenlabs_key_slots: elevenLabsTrace?.keySlots || [],
                        elevenlabs_model_ids: elevenLabsTrace?.modelIds || [],
                        generated_by: auth.requester.email,
                        web_view_link: driveFile.webViewLink || driveFileLink(driveFile.id),
                    },
                })
                .select('*')
                .single()
            if (assetError) throw assetError
            asset = insertedAsset
        } catch (assetError: any) {
            console.warn('[STD TTS] asset row could not be saved; continuing with Drive file playback', assetError?.message)
        }

        const progressPayload = project.progress_payload || {}
        stage = 'update_project_tts_state'
        await supabaseAdmin
            .from('std_projects')
            .update({
                drive_folder_id: folders.projectFolderId,
                progress_payload: {
                    ...progressPayload,
                    std_drive: {
                        ...(progressPayload.std_drive || {}),
                        folder_ids: {
                            project: folders.projectFolderId,
                            images: folders.imagesFolderId,
                            videos: folders.videosFolderId,
                            originals: folders.originalsFolderId,
                        },
                    },
                    has_tts_audio: true,
                    tts_generated_at: now,
                    tts_asset_id: asset?.id || null,
                    tts_drive_file_id: driveFile.id,
                    tts_file_name: driveFile.name || fileName,
                    voice_id: voiceId,
                    tts_speed: projectTtsSpeed,
                    multi_voice: multiVoice,
                    voice_map: voiceMap,
                    elevenlabs_key_slots: elevenLabsTrace?.keySlots || [],
                    elevenlabs_model_ids: elevenLabsTrace?.modelIds || [],
                },
                project_payload: {
                    ...(project.project_payload || {}),
                    audio_url: driveFile.webViewLink || driveFileLink(driveFile.id),
                    tts_url: driveFile.webViewLink || driveFileLink(driveFile.id),
                    voice_id: voiceId,
                    tts_speed: projectTtsSpeed,
                    multi_voice: multiVoice,
                    voice_map: voiceMap,
                },
                updated_at: now,
            })
            .eq('id', project.id)

        try {
            stage = 'sync_legacy'
            await syncStdProjectToLegacy(project.id)
        } catch {}

        const audioUrl = asset?.id
            ? `/api/std/projects/${encodeURIComponent(project.id)}/tts/audio?assetId=${encodeURIComponent(asset.id)}`
            : `/api/std/projects/${encodeURIComponent(project.id)}/tts/audio?driveFileId=${encodeURIComponent(driveFile.id)}`
        const inlineAudioUrl = audioBuffer.length <= MAX_INLINE_AUDIO_BYTES
            ? `data:audio/mpeg;base64,${audioBuffer.toString('base64')}`
            : ''

        return NextResponse.json({
            success: true,
            asset,
            drive_file: driveFile,
            audio_url: inlineAudioUrl || audioUrl,
            download_url: audioUrl,
            persisted_audio_url: audioUrl,
            web_view_link: driveFile.webViewLink || driveFileLink(driveFile.id),
            elevenlabs_key_slots: elevenLabsTrace?.keySlots || [],
            elevenlabs_model_ids: elevenLabsTrace?.modelIds || [],
            message: multiVoice ? '등장인물 멀티 보이스 TTS 음성이 성공적으로 생성되었습니다!' : 'TTS 음성이 성공적으로 생성되었습니다!',
        })
    } catch (error: any) {
        console.error('[STD TTS] generation failed', {
            projectId: project.id,
            stage,
            textLength: ttsDebug.textLength,
            chunkCount: ttsDebug.chunkCount,
            keyPreflight: ttsDebug.keyInspections,
            error: error?.message || String(error),
        })
        await recordStdTtsFailure({
            requester: auth.requester,
            project,
            stage,
            error,
            textLength: ttsDebug.textLength,
            chunkCount: ttsDebug.chunkCount,
            keyInspections: ttsDebug.keyInspections,
        })
        return NextResponse.json(
            {
                success: false,
                error: error?.message || 'TTS generation failed',
                stage,
                text_length: ttsDebug.textLength,
                chunk_count: ttsDebug.chunkCount,
                elevenlabs_key_preflight: ttsDebug.keyInspections,
            },
            { status: 500 }
        )
    }
}
