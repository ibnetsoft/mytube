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

export const dynamic = 'force-dynamic'
export const maxDuration = 300

const DEFAULT_ELEVENLABS_VOICE_ID = '4JJwo477JUAx3HV0T7n7'
const DEFAULT_ELEVENLABS_MODEL_ID = 'eleven_multilingual_v2'
const MAX_CHARS_PER_REQUEST = 4500
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

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

async function getGlobalSetting(key: string) {
    const { data, error } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', key)
        .maybeSingle()
    if (error) throw error
    return String(data?.value || '').trim()
}

async function generateSingleElevenLabsChunk(input: {
    apiKey: string
    voiceId: string
    modelId: string
    chunk: string
    speed?: number
    stability?: number
    similarityBoost?: number
    style?: number
}): Promise<Buffer> {
    const voiceSettings: Record<string, number> = {}
    if (Number.isFinite(input.stability)) voiceSettings.stability = Number(input.stability)
    if (Number.isFinite(input.similarityBoost)) voiceSettings.similarity_boost = Number(input.similarityBoost)
    if (Number.isFinite(input.style)) voiceSettings.style = Number(input.style)
    if (Number.isFinite(input.speed)) voiceSettings.speed = Math.min(1.2, Math.max(0.7, Number(input.speed)))

    const res = await fetch(
        `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(input.voiceId)}?output_format=mp3_44100_128`,
        {
            method: 'POST',
            headers: {
                'xi-api-key': input.apiKey,
                'Content-Type': 'application/json',
                Accept: 'audio/mpeg',
            },
            body: JSON.stringify({
                text: input.chunk,
                model_id: input.modelId || DEFAULT_ELEVENLABS_MODEL_ID,
                voice_settings: Object.keys(voiceSettings).length ? voiceSettings : undefined,
            }),
        }
    )

    if (!res.ok) {
        const errText = await res.text()
        throw new Error(`ElevenLabs TTS API error (${res.status}): ${errText}`)
    }

    const arrayBuffer = await res.arrayBuffer()
    return Buffer.from(arrayBuffer)
}

async function generateElevenLabsMp3(input: {
    apiKey: string
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
    // 1. 멀티 보이스 모드인 경우
    if (input.multiVoice && input.voiceMap && Object.keys(input.voiceMap).length > 0) {
        const { segments } = parseScriptToVoiceSegments(input.text)
        if (!segments.length) throw new Error('TTS multi-voice text has no segments')

        const buffers: Buffer[] = []
        for (const seg of segments) {
            const targetVoiceId = input.voiceMap[seg.speaker] || input.voiceId || DEFAULT_ELEVENLABS_VOICE_ID
            const chunks = splitText(seg.text)
            for (const chunk of chunks) {
                const buf = await generateSingleElevenLabsChunk({
                    apiKey: input.apiKey,
                    voiceId: targetVoiceId,
                    modelId: input.modelId,
                    chunk,
                    speed: input.speed,
                    stability: input.stability,
                    similarityBoost: input.similarityBoost,
                    style: input.style,
                })
                buffers.push(buf)
            }
        }
        return Buffer.concat(buffers)
    }

    // 2. 단일 보이스 모드
    const chunks = splitText(input.text)
    if (!chunks.length) throw new Error('TTS text is empty')

    const buffers: Buffer[] = []
    for (const chunk of chunks) {
        const buf = await generateSingleElevenLabsChunk({
            apiKey: input.apiKey,
            voiceId: input.voiceId,
            modelId: input.modelId,
            chunk,
            speed: input.speed,
            stability: input.stability,
            similarityBoost: input.similarityBoost,
            style: input.style,
        })
        buffers.push(buf)
    }

    return Buffer.concat(buffers)
}

async function generateSingleGoogleTranslateChunk(chunk: string): Promise<Buffer> {
    const url = new URL('https://translate.google.com/translate_tts')
    url.searchParams.set('ie', 'UTF-8')
    url.searchParams.set('client', 'tw-ob')
    url.searchParams.set('tl', 'ko')
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

async function generateGoogleFreeMp3(text: string) {
    const chunks = splitText(text, 180)
    if (!chunks.length) throw new Error('TTS text is empty')

    const buffers: Buffer[] = []
    for (const chunk of chunks) {
        buffers.push(await generateSingleGoogleTranslateChunk(chunk))
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

function topicIdFromProjectParam(projectId: string) {
    const value = String(projectId || '').trim()
    const legacyMatch = value.match(/^proj--?(\d+)$/i)
    if (legacyMatch) return Number(legacyMatch[1])

    const numeric = Number(value)
    if (Number.isFinite(numeric) && numeric >= 1_000_000_000) return numeric - 1_000_000_000
    return null
}

async function loadStdProject(projectId: string, employeeEmail: string) {
    let query = supabaseAdmin.from('std_projects').select('*').eq('employee_email', employeeEmail)
    const topicQueueId = topicIdFromProjectParam(projectId)

    if (UUID_RE.test(projectId)) {
        query = query.eq('id', projectId)
    } else if (topicQueueId != null && Number.isFinite(topicQueueId)) {
        query = query.eq('topic_queue_id', topicQueueId)
    } else {
        return { data: null, error: null }
    }

    return await query.maybeSingle()
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
        const multiVoice = Boolean(body?.multi_voice)
        const voiceMap = body?.voice_map || {}

        let audioBuffer: Buffer
        if (provider === 'google_free' || voiceId.startsWith('google_')) {
            stage = 'generate_google_free'
            audioBuffer = await generateGoogleFreeMp3(text)
        } else {
            stage = 'load_elevenlabs_key'
            let apiKey = ''
            try {
                apiKey = await getGlobalSetting('sys_api_elevenlabs')
            } catch {
                apiKey = ''
            }
            if (!apiKey) {
                apiKey = process.env.ELEVENLABS_API_KEY || ''
            }
            if (!apiKey) {
                return NextResponse.json({ success: false, error: 'ElevenLabs API key is not configured' }, { status: 500 })
            }

            stage = 'generate_elevenlabs'
            audioBuffer = await generateElevenLabsMp3({
                apiKey,
                voiceId,
                modelId,
                text,
                speed: Number(body?.speed || 1),
                stability: body?.stability == null ? undefined : Number(body.stability),
                similarityBoost: body?.similarity_boost == null ? undefined : Number(body.similarity_boost),
                style: body?.style == null ? undefined : Number(body.style),
                multiVoice,
                voiceMap,
            })
        }

        const now = new Date().toISOString()
        const safeProjectKey = String(project.topic_queue_id || project.id).replace(/[^a-zA-Z0-9_-]/g, '')
        const fileName = `std_tts_${safeProjectKey}_${Date.now()}.mp3`
        stage = 'ensure_drive_folders'
        let folders: Awaited<ReturnType<typeof ensureStdProjectDriveFolders>>
        try {
            folders = await ensureStdProjectDriveFolders(project)
        } catch (driveConfigError: any) {
            if (driveConfigError?.message === 'drive_root_folder_not_configured') {
                const audioDataUrl = `data:audio/mpeg;base64,${audioBuffer.toString('base64')}`
                return NextResponse.json({
                    success: true,
                    asset: null,
                    drive_file: null,
                    audio_url: audioDataUrl,
                    download_url: audioDataUrl,
                    web_view_link: null,
                    transient: true,
                    message: 'TTS audio generated for immediate playback. Drive storage is not configured.',
                })
            }
            throw driveConfigError
        }
        stage = 'upload_drive_file'
        const driveFile = await uploadStdDriveBuffer(
            folders.originalsFolderId,
            fileName,
            audioBuffer,
            'audio/mpeg',
            `AIR STD web TTS audio for project ${project.id}`
        )

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
                        multi_voice: multiVoice,
                        voice_map: voiceMap,
                        text_length: text.length,
                        chunk_count: splitText(text).length,
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
                    has_tts_audio: true,
                    tts_generated_at: now,
                    tts_asset_id: asset?.id || null,
                    tts_drive_file_id: driveFile.id,
                    tts_file_name: driveFile.name || fileName,
                    voice_id: voiceId,
                    multi_voice: multiVoice,
                    voice_map: voiceMap,
                },
                project_payload: {
                    ...(project.project_payload || {}),
                    audio_url: driveFile.webViewLink || driveFileLink(driveFile.id),
                    tts_url: driveFile.webViewLink || driveFileLink(driveFile.id),
                    voice_id: voiceId,
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

        return NextResponse.json({
            success: true,
            asset,
            drive_file: driveFile,
            audio_url: audioUrl,
            download_url: audioUrl,
            web_view_link: driveFile.webViewLink || driveFileLink(driveFile.id),
            message: multiVoice ? '등장인물 멀티 보이스 TTS 음성이 성공적으로 생성되었습니다!' : 'TTS 음성이 성공적으로 생성되었습니다!',
        })
    } catch (error: any) {
        return NextResponse.json(
            { success: false, error: error?.message || 'TTS generation failed', stage },
            { status: 500 }
        )
    }
}
