import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import {
    driveFileLink,
    ensureStdProjectDriveFolders,
    uploadStdDriveBuffer,
} from '@/lib/stdGoogleDrive'
import { syncStdProjectToLegacy } from '@/lib/stdLegacySync'

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

async function generateElevenLabsMp3(input: {
    apiKey: string
    voiceId: string
    modelId: string
    text: string
    speed?: number
    stability?: number
    similarityBoost?: number
    style?: number
}) {
    const chunks = splitText(input.text)
    if (!chunks.length) throw new Error('TTS text is empty')

    const buffers: Buffer[] = []
    for (const chunk of chunks) {
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
                    text: chunk,
                    model_id: input.modelId,
                    voice_settings: Object.keys(voiceSettings).length ? voiceSettings : undefined,
                }),
            }
        )
        if (!res.ok) {
            const detail = await res.text()
            throw new Error(`ElevenLabs TTS failed: HTTP ${res.status} ${detail.slice(0, 240)}`)
        }
        buffers.push(Buffer.from(await res.arrayBuffer()))
    }
    return Buffer.concat(buffers)
}

function buildTtsText(project: any, scenes: any[], requestedText?: string) {
    const explicit = cleanTtsText(requestedText || '')
    if (explicit) return explicit
    const sceneText = scenes
        .map((scene: any) => cleanTtsText(scene.scene_text || scene.metadata?.narration || scene.metadata?.script || ''))
        .filter(Boolean)
        .join('\n\n')
    return cleanTtsText(sceneText || project.project_payload?.script || '')
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    let body: any = {}
    try {
        body = await req.json()
    } catch {
        body = {}
    }

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })
    if (['review_requested', 'approved', 'canceled'].includes(project.status)) {
        return NextResponse.json({ success: false, error: 'Project is not editable' }, { status: 409 })
    }

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
            apiKey = process.env.ELEVENLABS_API_KEY || 'sk_d86b5fe40c6a6f7012affbc13135fa4adfc171eaf9c58332'
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

        const audioBuffer = await generateElevenLabsMp3({
            apiKey,
            voiceId,
            modelId,
            text,
            speed: Number(body?.speed || 1),
            stability: body?.stability == null ? undefined : Number(body.stability),
            similarityBoost: body?.similarity_boost == null ? undefined : Number(body.similarity_boost),
            style: body?.style == null ? undefined : Number(body.style),
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
                    tts_voice_id: voiceId,
                    tts_model_id: modelId,
                    std_drive: {
                        ...(progressPayload.std_drive || {}),
                        folder_ids: {
                            project: folders.projectFolderId,
                            images: folders.imagesFolderId,
                            videos: folders.videosFolderId,
                            originals: folders.originalsFolderId,
                        },
                    },
                },
                status: project.status === 'claimed' ? 'in_progress' : project.status,
                updated_at: now,
            })
            .eq('id', project.id)

        try {
            await syncStdProjectToLegacy(project.id)
        } catch (syncError: any) {
            console.error('[STD TTS] legacy sync failed:', syncError?.message)
        }

        return NextResponse.json({
            success: true,
            asset: {
                ...asset,
                drive_file_link: driveFile.webViewLink || driveFileLink(driveFile.id),
            },
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'TTS generation failed' }, { status: 500 })
    }
}
