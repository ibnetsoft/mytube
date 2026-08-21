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
                current = sentence.length <= maxChars ? sentence : sentence.slice(0, maxChars)
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

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const body = await req.json().catch(() => ({}))

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    const { data: scenes, error: scenesError } = await supabaseAdmin
        .from('std_project_scenes')
        .select('*')
        .eq('project_id', project.id)
        .order('scene_number', { ascending: true })
    if (scenesError) return NextResponse.json({ success: false, error: scenesError.message }, { status: 500 })

    try {
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

        const text = buildTtsText(project, scenes || [], body?.text)
        if (!text) return NextResponse.json({ success: false, error: 'TTS text is empty' }, { status: 400 })

        const voiceId = String(
            body?.voice_id
            || project.progress_payload?.voice_id
            || project.project_payload?.voice_id
            || DEFAULT_ELEVENLABS_VOICE_ID
        ).trim()
        const modelId = String(body?.model_id || project.project_payload?.tts_model_id || DEFAULT_ELEVENLABS_MODEL_ID).trim()
        const multiVoice = Boolean(body?.multi_voice)
        const voiceMap = body?.voice_map || {}

        const audioBuffer = await generateElevenLabsMp3({
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

        const folders = await ensureStdProjectDriveFolders(project)
        const now = new Date().toISOString()
        const safeProjectKey = String(project.topic_queue_id || project.id).replace(/[^a-zA-Z0-9_-]/g, '')
        const fileName = `std_tts_${safeProjectKey}_${Date.now()}.mp3`
        const driveFile = await uploadStdDriveBuffer(
            folders.originalsFolderId,
            fileName,
            audioBuffer,
            'audio/mpeg',
            `AIR STD web TTS audio for project ${project.id}`
        )

        await supabaseAdmin
            .from('std_project_assets')
            .update({ status: 'replaced', updated_at: now })
            .eq('project_id', project.id)
            .eq('asset_type', 'audio')
            .in('status', ['uploaded', 'assigned'])

        const { data: asset, error: assetError } = await supabaseAdmin
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
                    provider: 'elevenlabs',
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

        const progressPayload = project.progress_payload || {}
        await supabaseAdmin
            .from('std_projects')
            .update({
                drive_folder_id: folders.projectFolderId,
                progress_payload: {
                    ...progressPayload,
                    has_tts_audio: true,
                    tts_generated_at: now,
                    tts_asset_id: asset.id,
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
            await syncStdProjectToLegacy(project.id)
        } catch {}

        const audioUrl = `/api/std/projects/${encodeURIComponent(project.id)}/tts/audio?assetId=${encodeURIComponent(asset.id)}`

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
            { success: false, error: error?.message || 'TTS generation failed' },
            { status: 500 }
        )
    }
}
