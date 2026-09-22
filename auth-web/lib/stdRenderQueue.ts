import { subtitleGain } from './stdSpeechGain'
import { resolveSfxCues } from '@/lib/stdSfxCues'
import { audioAssetRole } from './stdAudioMix'
import { sceneMotion, sceneMotionSpeed } from './stdSceneMotion'
import { randomUUID } from 'crypto'
import { supabaseAdmin } from './supabaseAdmin'
import { isStdRequiredVideoScene } from './stdPolicy'
import { nextStdRenderVersion, normalizeStdRenderHistory } from './stdRenderVersion'
import {
    createGcsSignedReadUrl,
    downloadGcsObject,
    isGcsStorageConfigured,
    isGcsConfiguredAsync,
    gcsBucketName,
    uploadGcsBuffer,
} from './gcsStorage'

type ZipEntry = {
    path: string
    data: Buffer
}

const CRC_TABLE = (() => {
    const table = new Uint32Array(256)
    for (let n = 0; n < 256; n += 1) {
        let c = n
        for (let k = 0; k < 8; k += 1) {
            c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
        }
        table[n] = c >>> 0
    }
    return table
})()

export function stdWebPseudoProjectId(topicQueueId: any): number {
    const parsed = Number(topicQueueId)
    if (!Number.isFinite(parsed) || parsed <= 0) return 1_900_000_000
    return 1_000_000_000 + Math.floor(parsed)
}

export async function getStdProjectRenderHistory(projectId: string) {
    const { data, error } = await supabaseAdmin
        .from('remote_render_queue')
        .select('id,status,progress,message,error_message,result_file_id,result_file_name,metadata,created_at,updated_at,completed_at,render_mode,asset_file_id,asset_file_name')
        .contains('metadata', { std_web_project_id: projectId })
        .order('created_at', { ascending: false })

    if (error) throw error
    return normalizeStdRenderHistory(data || [])
}

function activeAsset(asset: any) {
    return ['uploaded', 'assigned'].includes(String(asset?.status || ''))
}

function generatedImageStorageSource(scene: any) {
    const metadata = scene?.metadata && typeof scene.metadata === 'object' ? scene.metadata : {}
    const nestedMetadata = metadata?.metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {}
    const coworkAsset = metadata?.cowork_image_asset || nestedMetadata?.cowork_image_asset || {}
    const bucket = String(coworkAsset?.bucket || metadata?.storage_bucket || nestedMetadata?.storage_bucket || '').trim()
    const path = String(
        coworkAsset?.object_path
        || metadata?.storage_path
        || metadata?.storage_object_path
        || nestedMetadata?.storage_path
        || nestedMetadata?.storage_object_path
        || ''
    ).trim().replace(/^\/+/, '')
    return bucket && path ? { bucket, path } : null
}

function cleanMediaUrl(value: any): string {
    const str = String(value || '').trim()
    if (!str || str.startsWith('blob:')) return ''
    return str
}

function storageSourceFromSupabaseUrl(value: any) {
    const rawUrl = cleanMediaUrl(value)
    if (!rawUrl) return null
    try {
        const url = new URL(rawUrl)
        const match = url.pathname.match(/\/storage\/v1\/(?:object|render)\/(?:public|authenticated|sign)\/([^/]+)\/(.+)$/)
        if (!match) return null
        return {
            bucket: decodeURIComponent(match[1]),
            path: decodeURIComponent(match[2]).replace(/^\/+/, ''),
        }
    } catch {
        return null
    }
}

function generatedVideoStorageSource(scene: any) {
    const metadata = scene?.metadata && typeof scene.metadata === 'object' ? scene.metadata : {}
    const nestedMetadata = metadata?.metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {}
    const coworkAsset = metadata?.cowork_video_asset || nestedMetadata?.cowork_video_asset || {}
    const bucket = String(
        coworkAsset?.bucket
        || metadata?.video_storage_bucket
        || nestedMetadata?.video_storage_bucket
        || metadata?.storage_bucket
        || nestedMetadata?.storage_bucket
        || ''
    ).trim()
    const path = String(
        coworkAsset?.object_path
        || metadata?.video_storage_path
        || metadata?.video_storage_object_path
        || nestedMetadata?.video_storage_path
        || nestedMetadata?.video_storage_object_path
        || ''
    ).trim().replace(/^\/+/, '')
    if (bucket && path) return { bucket, path }

    return storageSourceFromSupabaseUrl(
        scene?.video_url
        || scene?.video
        || metadata?.video_url
        || metadata?.video
        || nestedMetadata?.video_url
        || nestedMetadata?.video
    )
}

function storageSourceForAsset(asset: any) {
    const metadata = asset?.metadata && typeof asset.metadata === 'object' ? asset.metadata : {}
    const nestedMetadata = metadata?.metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {}
    const bucket = String(metadata?.storage_bucket || nestedMetadata?.storage_bucket || 'content-assets').trim()
    const provider = String(metadata?.storage_provider || nestedMetadata?.storage_provider || '').trim().toLowerCase()
    const path = String(
        metadata?.storage_path
        || metadata?.storage_object_path
        || nestedMetadata?.storage_path
        || nestedMetadata?.storage_object_path
        || ''
    ).trim().replace(/^\/+/, '')
    const gcsBucket = String(metadata?.gcs_bucket || nestedMetadata?.gcs_bucket || (provider === 'gcs' ? bucket : '')).trim()
    const gcsPath = String(metadata?.gcs_path || nestedMetadata?.gcs_path || (provider === 'gcs' ? path : '')).trim().replace(/^\/+/, '')
    if (gcsPath) return { bucket, path: path || gcsPath, provider: 'gcs', gcsBucket, gcsPath }
    return null
}

async function storageManifestFields(storage: { bucket: string; path: string; provider?: string; gcsBucket?: string; gcsPath?: string } | null) {
    if (!storage) return {}
    const targetGcsPath = storage.gcsPath || storage.path
    const targetGcsBucket = storage.gcsBucket || storage.bucket
    let gcsSignedUrl: string | undefined
    if (targetGcsPath && (await isGcsConfiguredAsync())) {
        try {
            gcsSignedUrl = await createGcsSignedReadUrl({
                bucket: targetGcsBucket,
                objectPath: targetGcsPath,
                expiresInMinutes: 240,
            })
        } catch {
            // Signed URL generation optional
        }
    }
    return {
        storage_provider: 'gcs',
        storage_bucket: storage.bucket,
        storage_path: storage.path,
        gcs_bucket: targetGcsBucket || undefined,
        gcs_path: targetGcsPath || undefined,
        gcs_signed_url: gcsSignedUrl,
    }
}

async function downloadStorageSource(storage: { bucket: string; path: string; provider?: string; gcsBucket?: string; gcsPath?: string }) {
    const targetGcsPath = storage.gcsPath || storage.path
    const targetGcsBucket = storage.gcsBucket || storage.bucket
    if (targetGcsPath && isGcsStorageConfigured()) {
        try {
            return await downloadGcsObject({ bucket: targetGcsBucket, objectPath: targetGcsPath })
        } catch (gcsError: any) {
            console.warn('[stdRenderQueue] GCS download failed:', gcsError?.message)
        }
    }

    throw new Error('스토리지 파일을 GCS에서 불러오지 못했습니다.')
}

export async function ensureStdGeneratedSceneAssetsArchived(project: any, scenes: any[], assets: any[]) {
    const activeAssets = Array.isArray(assets) ? [...assets] : []
    const missingGeneratedVideos = (scenes || []).filter((scene: any) => {
        const sceneNumber = Number(scene?.scene_number)
        if (
            !Number.isFinite(sceneNumber)
            || sceneNumber <= 0
            || !isStdRequiredVideoScene(sceneNumber)
            || !generatedVideoStorageSource(scene)
        ) return false
        return !activeAssets.some((asset: any) => (
            activeAsset(asset)
            && String(asset?.asset_type || '').toLowerCase() === 'video'
            && Number(asset?.scene_number) === sceneNumber
            && storageSourceForAsset(asset)
        ))
    })

    for (const scene of missingGeneratedVideos) {
        const sceneNumber = Number(scene.scene_number)
        const source = generatedVideoStorageSource(scene)
        if (!source) continue
        const existingAsset = activeAssets.find((asset: any) => (
            String(asset?.asset_type || '').toLowerCase() === 'video'
            && Number(asset?.scene_number) === sceneNumber
        ))
        // Video recovery must archive the bytes too: the remote manifest uses GCS.
        const { data: videoFile, error: videoError } = await supabaseAdmin.storage.from(source.bucket).download(source.path)
        if (videoError || !videoFile) throw new Error(`Scene ${sceneNumber} video could not be read from Storage`)
        const gcsVideo = await uploadGcsBuffer({
            objectPath: source.path, data: Buffer.from(await videoFile.arrayBuffer()), contentType: 'video/mp4',
        })
        const metadata = {
            ...(existingAsset?.metadata || {}),
            secondary_storage_provider: 'gcs', gcs_bucket: gcsVideo.bucket, gcs_path: gcsVideo.path,
            storage_bucket: source.bucket,
            storage_path: source.path,
            storage_public_url: supabaseAdmin.storage.from(source.bucket).getPublicUrl(source.path).data.publicUrl,
            upload_mode: 'worker_generated_scene_video_recovered_for_render',
        }
        const assetPayload = {
            scene_id: scene?.id || existingAsset?.scene_id || null,
            scene_number: sceneNumber,
            asset_type: 'video',
            drive_file_id: null,
            drive_folder_id: null,
            file_name: existingAsset?.file_name || `scene_${String(sceneNumber).padStart(3, '0')}.mp4`,
            mime_type: existingAsset?.mime_type || 'video/mp4',
            file_size: existingAsset?.file_size || null,
            status: 'assigned',
            metadata,
            updated_at: new Date().toISOString(),
        }
        let recoveredAsset: any = null
        if (existingAsset?.id) {
            const { data, error } = await supabaseAdmin
                .from('std_project_assets')
                .update(assetPayload)
                .eq('id', existingAsset.id)
                .select('*')
                .single()
            if (error) throw new Error(error.message)
            recoveredAsset = data
            const index = activeAssets.findIndex((asset: any) => asset.id === existingAsset.id)
            if (index >= 0 && recoveredAsset) activeAssets[index] = recoveredAsset
        } else {
            const { data, error } = await supabaseAdmin
                .from('std_project_assets')
                .insert({ project_id: project.id, ...assetPayload })
                .select('*')
                .single()
            if (error) throw new Error(error.message)
            recoveredAsset = data
            if (recoveredAsset) activeAssets.push(recoveredAsset)
        }
    }

    const missingGeneratedImages = (scenes || []).filter((scene: any) => {
        const sceneNumber = Number(scene?.scene_number)
        if (
            !Number.isFinite(sceneNumber)
            || sceneNumber <= 0
            || isStdRequiredVideoScene(sceneNumber)
            || !generatedImageStorageSource(scene)
        ) return false
        return !activeAssets.some((asset: any) => (
            activeAsset(asset)
            && String(asset?.asset_type || '').toLowerCase() === 'image'
            && Number(asset?.scene_number) === sceneNumber
            && storageSourceForAsset(asset)
        ))
    })
    if (missingGeneratedImages.length === 0) return activeAssets

    const gcsConfigured = await isGcsConfiguredAsync()
    if (!gcsConfigured) {
        throw new Error('GCS is not configured for generated scene asset archiving.')
    }

    for (const scene of missingGeneratedImages) {
        const sceneNumber = Number(scene.scene_number)
        const source = generatedImageStorageSource(scene)
        if (!source) continue
        const { data: storageFile, error: storageError } = await supabaseAdmin.storage
            .from(source.bucket)
            .download(source.path)
        if (storageError || !storageFile) {
            throw new Error(`생성 이미지 ${sceneNumber}번을 Supabase Storage에서 읽을 수 없습니다: ${storageError?.message || 'missing file'}`)
        }

        const imageBuffer = Buffer.from(await storageFile.arrayBuffer())

        const gcsRes = await uploadGcsBuffer({
            objectPath: source.path,
            buffer: imageBuffer,
            contentType: 'image/png',
        })

        const existingAsset = activeAssets.find((asset: any) => (
            activeAsset(asset)
            && String(asset?.asset_type || '').toLowerCase() === 'image'
            && Number(asset?.scene_number) === sceneNumber
        ))
        const metadata = {
            ...(existingAsset?.metadata || {}),
            storage_bucket: source.bucket,
            storage_path: source.path,
            storage_public_url: supabaseAdmin.storage.from(source.bucket).getPublicUrl(source.path).data.publicUrl,
            storage_provider: 'gcs',
            gcs_bucket: gcsRes.bucket,
            gcs_path: gcsRes.path,
            upload_mode: 'worker_generated_gcs_archive',
        }
        const assetPayload = {
            scene_id: scene?.id || existingAsset?.scene_id || null,
            scene_number: sceneNumber,
            asset_type: 'image',
            drive_file_id: null,
            drive_folder_id: null,
            file_name: existingAsset?.file_name || `scene_${String(sceneNumber).padStart(3, '0')}.png`,
            mime_type: existingAsset?.mime_type || 'image/png',
            file_size: imageBuffer.length,
            status: 'assigned',
            metadata,
            updated_at: new Date().toISOString(),
        }
        let archivedAsset: any = null
        if (existingAsset?.id) {
            const { data, error } = await supabaseAdmin
                .from('std_project_assets')
                .update(assetPayload)
                .eq('id', existingAsset.id)
                .select('*')
                .single()
            if (error) throw new Error(error.message)
            archivedAsset = data
            const index = activeAssets.findIndex((asset: any) => asset.id === existingAsset.id)
            if (index >= 0 && archivedAsset) activeAssets[index] = archivedAsset
        } else {
            const { data, error } = await supabaseAdmin
                .from('std_project_assets')
                .insert({ project_id: project.id, ...assetPayload })
                .select('*')
                .single()
            if (error) throw new Error(error.message)
            archivedAsset = data
            if (archivedAsset) activeAssets.push(archivedAsset)
        }
    }
    return activeAssets
}

function isAudioAsset(asset: any) {
    const type = String(asset?.asset_type || '').toLowerCase()
    const mime = String(asset?.mime_type || '').toLowerCase()
    return type === 'audio' || mime.startsWith('audio/')
}

function mediaExtension(name: string, mimeType?: string | null, fallback = '.bin') {
    const match = String(name || '').match(/\.[a-z0-9]{1,8}$/i)
    if (match) return match[0].toLowerCase()
    const mime = String(mimeType || '').toLowerCase()
    if (mime.includes('png')) return '.png'
    if (mime.includes('jpeg') || mime.includes('jpg')) return '.jpg'
    if (mime.includes('webp')) return '.webp'
    if (mime.includes('mp4')) return '.mp4'
    if (mime.includes('quicktime')) return '.mov'
    if (mime.includes('mpeg') || mime.includes('mp3')) return '.mp3'
    if (mime.includes('wav')) return '.wav'
    return fallback
}

function clampNumber(value: any, fallback: number, min: number, max: number) {
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) return fallback
    return Math.max(min, Math.min(max, parsed))
}

function buildRenderSubtitles(project: any, scenes: any[]) {
    const savedSubtitles = Array.isArray(project?.project_payload?.subtitles)
        ? project.project_payload.subtitles
        : []
    const sourceSubtitles = savedSubtitles.length > 0
        ? savedSubtitles
        : (scenes || []).map((scene: any, index: number) => ({
            start: Number(scene?.metadata?.start ?? index * 5),
            end: Number(scene?.metadata?.end ?? (index + 1) * 5),
            text: String(scene?.scene_text || '').trim(),
        }))

    return sourceSubtitles.map((subtitle: any, index: number) => {
        const start = Number(subtitle?.start ?? subtitle?.start_num ?? subtitle?.start_time ?? index * 5)
        const end = Number(subtitle?.end ?? subtitle?.end_num ?? subtitle?.end_time ?? start + 5)
        const sceneNumber = Number(subtitle?.scene_number ?? subtitle?.scene ?? subtitle?.sceneNumber)
        return {
            start: Number.isFinite(start) ? start : index * 5,
            end: Number.isFinite(end) && end > start ? end : start + 5,
            text: String(subtitle?.text || '').trim(),
            volume: subtitleGain(subtitle) * 100,
            ...(Number.isFinite(sceneNumber) && sceneNumber > 0 ? { scene_number: sceneNumber } : {}),
            ...(subtitle?.voice_id || subtitle?.voiceId ? { voice_id: String(subtitle.voice_id || subtitle.voiceId) } : {}),
            ...(subtitle?.voice_name || subtitle?.voiceName ? { voice_name: String(subtitle.voice_name || subtitle.voiceName) } : {}),
            ...(subtitle?.direction ? { direction: String(subtitle.direction) } : {}),
        }
    }).filter((subtitle: any) => subtitle.text)
}

function sentenceComplete(text: string) {
    return /[.!?。！？…]["'”’)\]]*$/.test(String(text || '').trim())
}

function buildWorkerTtsPlan(project: any, subtitles: any[]) {
    const settings = {
        ...(project.project_payload?.settings || {}),
        ...(project.project_payload?.render_settings || {}),
    }
    const defaultVoiceId = String(
        project.project_payload?.voice_id
        || project.progress_payload?.voice_id
        || settings.voice_id
        || ''
    ).trim()
    const speed = Number(project.progress_payload?.tts_speed ?? project.project_payload?.tts_speed ?? settings.tts_speed ?? 1.0)
    const stability = Number(settings.tts_stability ?? settings.stability ?? project.project_payload?.stability ?? 0.7)
    const similarity = Number(settings.tts_similarity_boost ?? settings.similarity_boost ?? project.project_payload?.similarity_boost ?? 0.82)
    const style = Number(settings.tts_style ?? settings.style ?? project.project_payload?.style ?? 0.18)
    const language = String(project.language || project.project_payload?.language || project.project_payload?.target_language || 'ko')
    const enabled = settings.worker_tts_enabled !== false
    if (!enabled || !defaultVoiceId || !subtitles.length) return null

    const segments: any[] = []
    for (let index = 0; index < subtitles.length; index++) {
        const subtitle = subtitles[index]
        const voiceId = String(subtitle.voice_id || defaultVoiceId).trim()
        if (!voiceId) continue
        const direction = voiceId.startsWith('gemini:') ? String(subtitle.direction || settings.voice_direction || '').trim() : ''
        const previous = segments[segments.length - 1]
        const canMerge = previous
            && previous.voice_id === voiceId
            && previous.direction === direction
            && (previous.text.length < 350 || !sentenceComplete(previous.text))
        if (canMerge) {
            previous.text += ` ${subtitle.text}`
            previous.subtitle_indices.push(index)
            previous.scene_numbers.push(subtitle.scene_number || null)
        } else {
            segments.push({
                id: `seg_${String(segments.length + 1).padStart(4, '0')}`,
                text: subtitle.text,
                voice_id: voiceId,
                direction,
                subtitle_indices: [index],
                scene_numbers: [subtitle.scene_number || null],
            })
        }
    }
    if (!segments.length) return null
    return {
        enabled: true,
        provider: 'auto',
        language,
        speed: Number.isFinite(speed) ? Math.max(0.7, Math.min(1.3, speed)) : 1.0,
        stability: Number.isFinite(stability) ? Math.max(0, Math.min(1, stability)) : 0.7,
        similarity_boost: Number.isFinite(similarity) ? Math.max(0, Math.min(1, similarity)) : 0.82,
        style: Number.isFinite(style) ? Math.max(0, Math.min(1, style)) : 0.18,
        pause_complete_ms: 260,
        pause_incomplete_ms: 0,
        segments,
    }
}

function positiveNumber(value: any): number | null {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}

function buildSceneTimingStarts(scenes: any[], subtitles: any[]) {
    const result: number[] = []
    let cursor = 0
    for (let index = 0; index < scenes.length; index++) {
        const scene = scenes[index]
        const sceneNumber = Number(scene?.scene_number ?? index + 1)
        const sceneSubtitles = (subtitles || []).filter((subtitle: any) => Number(subtitle?.scene_number) === sceneNumber)
        const subtitleStart = sceneSubtitles.length
            ? Math.min(...sceneSubtitles.map((subtitle: any) => Number(subtitle.start)).filter(Number.isFinite))
            : null
        const sceneStart = Number.isFinite(Number(subtitleStart)) ? Math.max(0, Number(subtitleStart)) : cursor
        result.push(Math.round(sceneStart * 1000) / 1000)

        const subtitleEnd = sceneSubtitles.length
            ? Math.max(...sceneSubtitles.map((subtitle: any) => Number(subtitle.end)).filter(Number.isFinite))
            : null
        const sceneDuration = positiveNumber(scene?.duration_seconds ?? scene?.target_duration ?? scene?.metadata?.duration_seconds)
        cursor = Math.max(
            sceneStart + (sceneDuration || 0),
            Number.isFinite(Number(subtitleEnd)) ? Number(subtitleEnd) : 0,
            cursor
        )
    }
    return result
}

function audioManifestPath(asset: any, prefix: string, index = 0) {
    const ext = mediaExtension(asset?.file_name, asset?.mime_type, '.mp3')
    const safeId = String(asset?.id || asset?.drive_file_id || index || 'audio').replace(/[^a-z0-9_-]/gi, '').slice(0, 48)
    const suffix = index > 0 ? `${String(index).padStart(2, '0')}_` : ''
    return `audio/${prefix}_${suffix}${safeId}${ext}`
}

function crc32(buffer: Buffer) {
    let crc = 0xffffffff
    for (const byte of buffer) {
        crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8)
    }
    return (crc ^ 0xffffffff) >>> 0
}

function dosDateTime(date = new Date()) {
    const year = Math.max(1980, date.getFullYear())
    const dosTime = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2)
    const dosDate = ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate()
    return { dosTime, dosDate }
}

function createStoredZip(entries: ZipEntry[]) {
    const localParts: Buffer[] = []
    const centralParts: Buffer[] = []
    let offset = 0
    const { dosTime, dosDate } = dosDateTime()

    for (const entry of entries) {
        const name = Buffer.from(entry.path.replace(/\\/g, '/'), 'utf8')
        const data = entry.data
        const checksum = crc32(data)

        const local = Buffer.alloc(30)
        local.writeUInt32LE(0x04034b50, 0)
        local.writeUInt16LE(20, 4)
        local.writeUInt16LE(0x0800, 6)
        local.writeUInt16LE(0, 8)
        local.writeUInt16LE(dosTime, 10)
        local.writeUInt16LE(dosDate, 12)
        local.writeUInt32LE(checksum, 14)
        local.writeUInt32LE(data.length, 18)
        local.writeUInt32LE(data.length, 22)
        local.writeUInt16LE(name.length, 26)
        local.writeUInt16LE(0, 28)
        localParts.push(local, name, data)

        const central = Buffer.alloc(46)
        central.writeUInt32LE(0x02014b50, 0)
        central.writeUInt16LE(20, 4)
        central.writeUInt16LE(20, 6)
        central.writeUInt16LE(0x0800, 8)
        central.writeUInt16LE(0, 10)
        central.writeUInt16LE(dosTime, 12)
        central.writeUInt16LE(dosDate, 14)
        central.writeUInt32LE(checksum, 16)
        central.writeUInt32LE(data.length, 20)
        central.writeUInt32LE(data.length, 24)
        central.writeUInt16LE(name.length, 28)
        central.writeUInt16LE(0, 30)
        central.writeUInt16LE(0, 32)
        central.writeUInt16LE(0, 34)
        central.writeUInt16LE(0, 36)
        central.writeUInt32LE(0, 38)
        central.writeUInt32LE(offset, 42)
        centralParts.push(central, name)

        offset += local.length + name.length + data.length
    }

    const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0)
    const end = Buffer.alloc(22)
    end.writeUInt32LE(0x06054b50, 0)
    end.writeUInt16LE(0, 4)
    end.writeUInt16LE(0, 6)
    end.writeUInt16LE(entries.length, 8)
    end.writeUInt16LE(entries.length, 10)
    end.writeUInt32LE(centralSize, 12)
    end.writeUInt32LE(offset, 16)
    end.writeUInt16LE(0, 20)

    return Buffer.concat([...localParts, ...centralParts, end])
}

async function loadBundle(projectId: string) {
    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', projectId)
        .maybeSingle()
    if (projectError) throw projectError
    if (!project) throw new Error('Project not found')

    const [{ data: scenes, error: scenesError }, { data: assets, error: assetsError }] = await Promise.all([
        supabaseAdmin
            .from('std_project_scenes')
            .select('*')
            .eq('project_id', project.id)
            .order('scene_number', { ascending: true }),
        supabaseAdmin
            .from('std_project_assets')
            .select('*')
            .eq('project_id', project.id)
            .order('created_at', { ascending: false }),
    ])
    if (scenesError) throw scenesError
    if (assetsError) throw assetsError
    return { project, scenes: scenes || [], assets: assets || [] }
}

async function downloadRenderAudio(asset: any): Promise<Buffer> {
    const storage = storageSourceForAsset(asset)
    if (storage) {
        return downloadStorageSource(storage)
    }
    throw new Error('렌더용 오디오 파일의 GCS 저장 정보가 없습니다.')
}

async function buildLegacyRenderPackage(project: any, scenes: any[], assets: any[], pseudoProjectId: number) {
    const entries: ZipEntry[] = []
    const activeAssets = (assets || []).filter(activeAsset).map(asset => ({ ...asset, asset_type: audioAssetRole(asset) }))
    const sceneAssets = activeAssets.filter((asset: any) => ['image', 'video'].includes(String(asset.asset_type || '').toLowerCase()))
    const audioAsset = activeAssets.find(isAudioAsset)

    if (!storageSourceForAsset(audioAsset)) {
        throw new Error('렌더용 오디오 파일이 없습니다. GCS 저장 정보가 필요합니다.')
    }

    const audioExt = mediaExtension(audioAsset.file_name, audioAsset.mime_type, '.mp3')
    const audioFilename = `audio_${pseudoProjectId}${audioExt}`
    entries.push({
        path: `audio/${audioFilename}`,
        data: await downloadRenderAudio(audioAsset),
    })

    const images: Array<string | null> = []
    for (const scene of scenes) {
        const sceneNumber = Number(scene.scene_number)
        const videoAsset = sceneAssets.find((item: any) =>
            Number(item.scene_number) === sceneNumber
            && String(item.asset_type || '').toLowerCase() === 'video'
        )
        const imageAsset = sceneAssets.find((item: any) =>
            Number(item.scene_number) === sceneNumber
            && String(item.asset_type || '').toLowerCase() === 'image'
        )
        const asset = videoAsset || imageAsset
        const assetStorage = storageSourceForAsset(asset)
        if (!assetStorage) {
            throw new Error(`Scene ${sceneNumber} media is missing from render storage`)
        }
        const ext = mediaExtension(asset.file_name, asset.mime_type, '.png')
        const filename = `scene_${String(sceneNumber).padStart(3, '0')}${ext}`
        entries.push({
            path: `images/${filename}`,
            data: await downloadStorageSource(assetStorage),
        })
        images.push(filename)
    }

    const subtitles = buildRenderSubtitles(project, scenes)
    const imageTimingStarts = buildSceneTimingStarts(scenes, subtitles)
    const workerTts = buildWorkerTtsPlan(project, subtitles)

    const thumbnailAsset = activeAssets.find((asset: any) => String(asset.asset_type || '').toLowerCase() === 'thumbnail')
    let thumbnailFilename: string | null = null
    const thumbnailStorage = thumbnailAsset ? storageSourceForAsset(thumbnailAsset) : null
    if (thumbnailStorage) {
        const ext = mediaExtension(thumbnailAsset.file_name, thumbnailAsset.mime_type, '.png')
        thumbnailFilename = `thumbnail${ext}`
        entries.push({
            path: thumbnailFilename,
            data: await downloadStorageSource(thumbnailStorage),
        })
    }

    const renderSettings = {
        ...(project.project_payload?.settings || {}),
        ...(project.project_payload?.render_settings || {}),
        app_mode: 'longform',
        subtitle_bg_enabled: project.project_payload?.render_settings?.subtitle_bg_enabled
            ?? project.project_payload?.settings?.subtitle_bg_enabled
            ?? 1,
        bg_enabled: project.project_payload?.render_settings?.bg_enabled
            ?? project.project_payload?.settings?.bg_enabled
            ?? project.project_payload?.render_settings?.subtitle_bg_enabled
            ?? project.project_payload?.settings?.subtitle_bg_enabled
            ?? 1,
        subtitle_bg_color: project.project_payload?.render_settings?.subtitle_bg_color
            ?? project.project_payload?.settings?.subtitle_bg_color
            ?? project.project_payload?.render_settings?.bg_color
            ?? project.project_payload?.settings?.bg_color
            ?? '#000000',
        bg_color: project.project_payload?.render_settings?.bg_color
            ?? project.project_payload?.settings?.bg_color
            ?? project.project_payload?.render_settings?.subtitle_bg_color
            ?? project.project_payload?.settings?.subtitle_bg_color
            ?? '#000000',
        subtitle_bg_opacity: project.project_payload?.render_settings?.subtitle_bg_opacity
            ?? project.project_payload?.settings?.subtitle_bg_opacity
            ?? project.project_payload?.render_settings?.bg_opacity
            ?? project.project_payload?.settings?.bg_opacity
            ?? 0.5,
        bg_opacity: project.project_payload?.render_settings?.bg_opacity
            ?? project.project_payload?.settings?.bg_opacity
            ?? project.project_payload?.render_settings?.subtitle_bg_opacity
            ?? project.project_payload?.settings?.subtitle_bg_opacity
            ?? 0.5,
        title: project.title,
        language: project.language || 'ko',
    }

    const config = {
        project_id: pseudoProjectId,
        project_name: project.title || `Project ${pseudoProjectId}`,
        email: project.employee_email || 'unknown',
        use_subtitles: true,
        resolution: '1080p',
        aspect_ratio: '16:9',
        speech_gain_version: 1,
        audio_filename: audioFilename,
        audio_duration: project.progress_payload?.audio_duration || null,
        images,
        subtitles,
        worker_tts: workerTts,
        subtitle_sync_mode: 'preserve_subtitle_timings',
        render_settings: { ...renderSettings, scene_motion_speeds: scenes.map(sceneMotionSpeed) },
        image_timing_starts: imageTimingStarts,
        image_effects: scenes.map(sceneMotion),
        transition_effects: scenes.map((scene: any) => String(scene?.metadata?.transition_effect || scene?.transition_effect || '')),
        focal_point_ys: images.map(() => 0.5),
        bg_video_url: null,
        intro_filename: null,
        template_overlay_filename: null,
        content_aspect_ratio: null,
        app_mode: 'longform',
        thumbnail_filename: thumbnailFilename,
        project_upload_metadata: {
            title: project.project_payload?.publish_metadata?.title || project.title,
            description: project.project_payload?.publish_metadata?.description || '',
            hashtags: project.project_payload?.publish_metadata?.hashtags || '',
            status: 'ready_for_upload',
        },
    }

    entries.unshift({
        path: 'config.json',
        data: Buffer.from(JSON.stringify(config, null, 4), 'utf8'),
    })

    return createStoredZip(entries)
}

async function buildGcsRenderConfig(project: any, scenes: any[], assets: any[], pseudoProjectId: number) {
    const activeAssets = (assets || []).filter(activeAsset).map(asset => ({ ...asset, asset_type: audioAssetRole(asset) }))
    const sceneAssets = activeAssets.filter((asset: any) => ['image', 'video'].includes(String(asset.asset_type || '').toLowerCase()))
    const audioAsset = activeAssets.find(isAudioAsset)

    if (!storageSourceForAsset(audioAsset)) {
        throw new Error('렌더용 오디오 파일이 없습니다. GCS 저장 정보가 필요합니다.')
    }

    const manifestFiles: any[] = []
    const audioExt = mediaExtension(audioAsset.file_name, audioAsset.mime_type, '.mp3')
    const audioFilename = `audio_${pseudoProjectId}${audioExt}`
    const audioStorage = storageSourceForAsset(audioAsset)
    manifestFiles.push({
        asset_type: 'audio',
        path: `audio/${audioFilename}`,
        file_name: audioAsset.file_name,
        mime_type: audioAsset.mime_type,
        size: audioAsset.file_size || null,
        ...(await storageManifestFields(audioStorage)),
    })

    const images: Array<string | null> = []
    for (const scene of scenes) {
        const sceneNumber = Number(scene.scene_number)
        const videoAsset = sceneAssets.find((item: any) =>
            Number(item.scene_number) === sceneNumber
            && String(item.asset_type || '').toLowerCase() === 'video'
        )
        const imageAsset = sceneAssets.find((item: any) =>
            Number(item.scene_number) === sceneNumber
            && String(item.asset_type || '').toLowerCase() === 'image'
        )
        const asset = videoAsset || imageAsset
        const assetStorage = storageSourceForAsset(asset)
        if (!assetStorage) {
            throw new Error(`Scene ${sceneNumber} media is missing from render storage`)
        }
        const ext = mediaExtension(asset.file_name, asset.mime_type, '.png')
        const filename = `scene_${String(sceneNumber).padStart(3, '0')}${ext}`
        images.push(filename)
        manifestFiles.push({
            asset_type: String(asset.asset_type || '').toLowerCase(),
            scene_number: sceneNumber,
            path: `images/${filename}`,
            file_name: asset.file_name,
            mime_type: asset.mime_type,
            size: asset.file_size || null,
            ...(await storageManifestFields(assetStorage)),
        })
    }

    const subtitles = buildRenderSubtitles(project, scenes)
    const imageTimingStarts = buildSceneTimingStarts(scenes, subtitles)
    const workerTts = buildWorkerTtsPlan(project, subtitles)

    const thumbnailAsset = activeAssets.find((asset: any) => String(asset.asset_type || '').toLowerCase() === 'thumbnail')
    let thumbnailFilename: string | null = null
    const thumbnailStorage = thumbnailAsset ? storageSourceForAsset(thumbnailAsset) : null
    if (thumbnailStorage) {
        const ext = mediaExtension(thumbnailAsset.file_name, thumbnailAsset.mime_type, '.png')
        thumbnailFilename = `thumbnail${ext}`
        manifestFiles.push({
            asset_type: 'thumbnail',
            path: thumbnailFilename,
            file_name: thumbnailAsset.file_name,
            mime_type: thumbnailAsset.mime_type,
            size: thumbnailAsset.file_size || null,
            ...(await storageManifestFields(thumbnailStorage)),
        })
    }

    const projectRenderSettings = {
        ...(project.project_payload?.settings || {}),
        ...(project.project_payload?.render_settings || {}),
    }
    const audioEffectAssets = activeAssets.filter((asset: any) => {
        const type = String(asset.asset_type || '').toLowerCase()
        return ['bgm', 'sfx'].includes(type) && storageSourceForAsset(asset)
    })
    const assetById = new Map(audioEffectAssets.map((asset: any) => [String(asset.id), asset]))
    const bgmAssetId = String(projectRenderSettings.bgm_asset_id || project.project_payload?.bgm_asset_id || '').trim()
    const bgmAsset = bgmAssetId ? assetById.get(bgmAssetId) : null
    let bgmPath = ''
    if (Number(projectRenderSettings.bgm_volume ?? 0.08) > 0 && bgmAsset) {
        bgmPath = audioManifestPath(bgmAsset, 'bgm')
        const bgmStorage = storageSourceForAsset(bgmAsset)
        manifestFiles.push({
            asset_type: 'bgm',
            path: bgmPath,
            file_name: bgmAsset.file_name || projectRenderSettings.bgm_file_name || 'library-bgm.mp3',
            mime_type: bgmAsset.mime_type || 'audio/mpeg',
            size: bgmAsset.file_size || null,
            ...(await storageManifestFields(bgmStorage)),
        })
    }

    const savedSfxCues = Array.isArray(projectRenderSettings.sfx_cues)
        ? projectRenderSettings.sfx_cues
        : (Array.isArray(project.project_payload?.sfx_cues) ? project.project_payload.sfx_cues : [])
    const sfxCues: any[] = []
    const resolvedCues = resolveSfxCues(savedSfxCues, project.project_payload?.subtitles || subtitles)
    for (let index = 0; index < resolvedCues.length; index++) {
        const cue = resolvedCues[index]
        if (!cue || cue.enabled === false) continue
        const assetId = String(cue.asset_id || '').trim()
        const asset = assetId ? assetById.get(assetId) : null
        const libraryKey = String(cue.library_key || cue.key || '').trim()
        if (!storageSourceForAsset(asset)) {
            if (!libraryKey) continue
            sfxCues.push({
                ...cue,
                library_key: libraryKey,
                key: libraryKey,
                start: clampNumber(cue.start ?? cue.time, 0, 0, 24 * 60 * 60),
                volume_db: clampNumber(cue.volume_db, -18, -60, 12),
            })
            continue
        }
        const path = audioManifestPath(asset, 'sfx', index + 1)
        const sfxStorage = storageSourceForAsset(asset)
        manifestFiles.push({
            asset_type: 'sfx',
            scene_number: Number(cue.scene_number) || null,
            subtitle_index: Number.isFinite(Number(cue.subtitle_index)) ? Number(cue.subtitle_index) : null,
            path,
            file_name: asset.file_name,
            mime_type: asset.mime_type,
            size: asset.file_size || null,
            ...(await storageManifestFields(sfxStorage)),
        })
        sfxCues.push({
            ...cue,
            path,
            filename: path,
            key: undefined,
            start: clampNumber(cue.start ?? cue.time, 0, 0, 24 * 60 * 60),
            volume_db: clampNumber(cue.volume_db, -18, -60, 12),
        })
    }

    const renderSettings = {
        ...projectRenderSettings,
        app_mode: 'longform',
        subtitle_bg_enabled: project.project_payload?.render_settings?.subtitle_bg_enabled
            ?? project.project_payload?.settings?.subtitle_bg_enabled
            ?? 1,
        bg_enabled: project.project_payload?.render_settings?.bg_enabled
            ?? project.project_payload?.settings?.bg_enabled
            ?? project.project_payload?.render_settings?.subtitle_bg_enabled
            ?? project.project_payload?.settings?.subtitle_bg_enabled
            ?? 1,
        subtitle_bg_color: project.project_payload?.render_settings?.subtitle_bg_color
            ?? project.project_payload?.settings?.subtitle_bg_color
            ?? project.project_payload?.render_settings?.bg_color
            ?? project.project_payload?.settings?.bg_color
            ?? '#000000',
        bg_color: project.project_payload?.render_settings?.bg_color
            ?? project.project_payload?.settings?.bg_color
            ?? project.project_payload?.render_settings?.subtitle_bg_color
            ?? project.project_payload?.settings?.subtitle_bg_color
            ?? '#000000',
        subtitle_bg_opacity: project.project_payload?.render_settings?.subtitle_bg_opacity
            ?? project.project_payload?.settings?.subtitle_bg_opacity
            ?? project.project_payload?.render_settings?.bg_opacity
            ?? project.project_payload?.settings?.bg_opacity
            ?? 0.5,
        bg_opacity: project.project_payload?.render_settings?.bg_opacity
            ?? project.project_payload?.settings?.bg_opacity
            ?? project.project_payload?.render_settings?.subtitle_bg_opacity
            ?? project.project_payload?.settings?.subtitle_bg_opacity
            ?? 0.5,
        title: project.title,
        language: project.language || 'ko',
        ...(bgmPath ? {
            bgm_path: bgmPath,
            bgm_volume: clampNumber(projectRenderSettings.bgm_volume, 0.08, 0, 1),
            bgm_loop: projectRenderSettings.bgm_loop !== false,
        } : {}),
    }

    return {
        project_id: pseudoProjectId,
        project_name: project.title || `Project ${pseudoProjectId}`,
        email: project.employee_email || 'unknown',
        use_subtitles: true,
        resolution: '1080p',
        aspect_ratio: '16:9',
        speech_gain_version: 1,
        audio_filename: audioFilename,
        audio_duration: project.progress_payload?.audio_duration || null,
        images,
        subtitles,
        worker_tts: workerTts,
        subtitle_sync_mode: 'preserve_subtitle_timings',
        render_settings: { ...renderSettings, scene_motion_speeds: scenes.map(sceneMotionSpeed) },
        image_timing_starts: imageTimingStarts,
        image_effects: scenes.map(sceneMotion),
        transition_effects: scenes.map((scene: any) => String(scene?.metadata?.transition_effect || scene?.transition_effect || '')),
        focal_point_ys: images.map(() => 0.5),
        bg_video_url: null,
        intro_filename: null,
        template_overlay_filename: null,
        content_aspect_ratio: null,
        app_mode: 'longform',
        thumbnail_filename: thumbnailFilename,
        sfx_cues: sfxCues,
        asset_manifest: {
            version: 1,
            transport: 'gcs_manifest',
            files: manifestFiles,
        },
        project_upload_metadata: {
            title: project.project_payload?.publish_metadata?.title || project.title,
            description: project.project_payload?.publish_metadata?.description || '',
            hashtags: project.project_payload?.publish_metadata?.hashtags || '',
            status: 'ready_for_upload',
        },
    }
}

export async function enqueueStdProjectRender(projectId: string) {
    const { project, scenes, assets } = await loadBundle(projectId)
    if (!project.topic_queue_id) throw new Error('Project has no topic_queue_id')

    const { data: activeRows, error: activeRowsError } = await supabaseAdmin
        .from('remote_render_queue')
        .select('*')
        .contains('metadata', { std_web_project_id: project.id })
        .in('status', ['pending', 'rendering'])
        .order('created_at', { ascending: false })
    if (activeRowsError) throw activeRowsError
    const existingRow = (activeRows || [])[0]
    if (existingRow) return existingRow

    const renderHistory = await getStdProjectRenderHistory(project.id)
    const renderVersion = nextStdRenderVersion(renderHistory)
    const previousRender = renderHistory[0] || null

    const pseudoProjectId = stdWebPseudoProjectId(project.topic_queue_id)
    const taskId = randomUUID()

    const archivedAssets = await ensureStdGeneratedSceneAssetsArchived(project, scenes, assets)
    const renderConfig = {
        ...(await buildGcsRenderConfig(project, scenes, archivedAssets, pseudoProjectId)),
        render_version: renderVersion,
        std_web_project_id: project.id,
    }

    const configStoragePath = `std-projects/${project.id}/render-packages/${taskId}/config.json`
    const configJsonBuffer = Buffer.from(JSON.stringify(renderConfig, null, 2), 'utf8')

    let gcsConfigSignedUrl: string | undefined
    if (await isGcsConfiguredAsync()) {
        try {
            await uploadGcsBuffer({
                objectPath: configStoragePath,
                data: configJsonBuffer,
                contentType: 'application/json',
            })
            gcsConfigSignedUrl = await createGcsSignedReadUrl({
                objectPath: configStoragePath,
                expiresInMinutes: 240,
            })
        } catch (gcsErr: any) {
            console.warn('[STD RenderQueue] GCS config upload failed:', gcsErr?.message || gcsErr)
        }
    }
    if (!gcsConfigSignedUrl) {
        throw new Error('GCS config upload failed. Remote render requires a GCS signed config URL.')
    }

    const metadata = {
        queue_scope: 'remote_render',
        worker_platform: 'korea_render_pc',
        upload_owner: 'web_admin',
        publish_owner: 'web_admin',
        visibility_control: 'web_admin_pending',
        package_transport: 'gcs_config',
        job_stage: 'pending',
        asset_file_id: taskId,
        asset_file_name: 'config.json',
        asset_file_size: configJsonBuffer.length,
        asset_web_link: gcsConfigSignedUrl,
        config_file_id: taskId,
        config_file_name: 'config.json',
        config_file_size: configJsonBuffer.length,
        config_web_link: gcsConfigSignedUrl,
        gcs_config: {
            bucket: gcsBucketName(),
            path: configStoragePath,
            signed_url: gcsConfigSignedUrl,
        },
        storage_provider: 'gcs',
        manifest_file_count: renderConfig.asset_manifest.files.length,
        source: 'picadiri_local_app',
        std_web_project_id: project.id,
        render_version: renderVersion,
        previous_render_queue_id: previousRender?.id || null,
        topic_queue_id: project.topic_queue_id,
        admin_publish_ready: false,
        admin_publish_status: 'render_pending',
    }

    const now = new Date().toISOString()
    const payload = {
        id: taskId,
        project_id: pseudoProjectId,
        project_name: project.title || `Project ${pseudoProjectId}`,
        email: project.employee_email || 'unknown',
        status: 'pending',
        progress: 0,
        message: 'GCS config manifest ready. Waiting for remote render.',
        render_mode: 'gcs_api',
        asset_file_id: taskId,
        asset_file_name: 'config.json',
        metadata,
        updated_at: now,
    }

    const { data: row, error } = await supabaseAdmin
        .from('remote_render_queue')
        .insert(payload)
        .select()
        .single()
    if (error) throw error

    await Promise.all([
        supabaseAdmin
            .from('topics_queue')
            .update({
                local_project_id: pseudoProjectId,
                progress_updated_at: now,
            })
            .eq('id', project.topic_queue_id),
        supabaseAdmin
            .from('std_projects')
            .update({
                progress_payload: {
                    ...(project.progress_payload || {}),
                    remote_task_id: taskId,
                    remote_render_queue_id: taskId,
                    remote_render_mode: 'gcs_api',
                    remote_asset_file_id: taskId,
                    remote_asset_file_name: 'config.json',
                    remote_asset_web_link: gcsConfigSignedUrl,
                    remote_render_queue_payload: payload,
                    latest_render_version: renderVersion,
                    editing_render_version: null,
                    rerender_draft: false,
                    admin_publish_status: 'render_pending',
                    submitted_to_render_queue_at: now,
                },
                updated_at: now,
            })
            .eq('id', project.id),
    ])

    return row
}
