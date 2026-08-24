import { randomUUID } from 'crypto'
import { supabaseAdmin } from './supabaseAdmin'
import {
    downloadStdDriveFile,
    driveFileLink,
    driveFolderLink,
    ensureStdProjectDriveFolders,
    sanitizeDriveName,
    uploadStdDriveBuffer,
} from './stdGoogleDrive'

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

function activeAsset(asset: any) {
    return ['uploaded', 'assigned'].includes(String(asset?.status || ''))
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

async function buildLegacyRenderPackage(project: any, scenes: any[], assets: any[], pseudoProjectId: number) {
    const entries: ZipEntry[] = []
    const activeAssets = (assets || []).filter(activeAsset)
    const sceneAssets = activeAssets.filter((asset: any) => ['image', 'video'].includes(String(asset.asset_type || '').toLowerCase()))
    const audioAsset = activeAssets.find(isAudioAsset)

    if (!audioAsset?.drive_file_id) {
        throw new Error('렌더용 오디오 파일이 없습니다. 기존 렌더 큐와 동일하게 제출하려면 ZIP 안에 audio/* TTS 파일이 필요합니다.')
    }

    const audioExt = mediaExtension(audioAsset.file_name, audioAsset.mime_type, '.mp3')
    const audioFilename = `audio_${pseudoProjectId}${audioExt}`
    entries.push({
        path: `audio/${audioFilename}`,
        data: await downloadStdDriveFile(audioAsset.drive_file_id),
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
        if (!asset?.drive_file_id) {
            images.push(null)
            continue
        }
        const ext = mediaExtension(asset.file_name, asset.mime_type, '.png')
        const filename = `scene_${String(sceneNumber).padStart(3, '0')}${ext}`
        entries.push({
            path: `images/${filename}`,
            data: await downloadStdDriveFile(asset.drive_file_id),
        })
        images.push(filename)
    }

    const subtitles = scenes.map((scene: any, index: number) => {
        const start = Number(scene?.metadata?.start ?? index * 5)
        const end = Number(scene?.metadata?.end ?? start + 5)
        return {
            start,
            end,
            text: String(scene?.scene_text || '').trim(),
        }
    }).filter((subtitle: any) => subtitle.text)

    const thumbnailAsset = activeAssets.find((asset: any) => String(asset.asset_type || '').toLowerCase() === 'thumbnail')
    let thumbnailFilename: string | null = null
    if (thumbnailAsset?.drive_file_id) {
        const ext = mediaExtension(thumbnailAsset.file_name, thumbnailAsset.mime_type, '.png')
        thumbnailFilename = `thumbnail${ext}`
        entries.push({
            path: thumbnailFilename,
            data: await downloadStdDriveFile(thumbnailAsset.drive_file_id),
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
        audio_filename: audioFilename,
        audio_duration: project.progress_payload?.audio_duration || null,
        images,
        subtitles,
        render_settings: renderSettings,
        image_timing_starts: null,
        image_effects: images.map(() => 'auto_classify'),
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

export async function enqueueStdProjectRender(projectId: string) {
    const { project, scenes, assets } = await loadBundle(projectId)
    if (!project.topic_queue_id) throw new Error('Project has no topic_queue_id')

    const { data: existingRows } = await supabaseAdmin
        .from('remote_render_queue')
        .select('*')
        .eq('status', 'pending')
        .eq('render_mode', 'drive_api')
        .order('created_at', { ascending: false })
        .limit(100)
    const existingRow = (existingRows || []).find((row: any) => row?.metadata?.std_web_project_id === project.id)
    if (existingRow) {
        return existingRow
    }

    const pseudoProjectId = stdWebPseudoProjectId(project.topic_queue_id)
    const folders = await ensureStdProjectDriveFolders(project)
    const packageBuffer = await buildLegacyRenderPackage(project, scenes, assets, pseudoProjectId)
    const packageName = sanitizeDriveName(`remote_render_pkg_${pseudoProjectId}.zip`, 'remote_render_pkg.zip')
    const driveFile = await uploadStdDriveBuffer(
        folders.projectFolderId,
        packageName,
        packageBuffer,
        'application/zip',
        `AIR remote render asset package for project ${pseudoProjectId}`
    )

    const metadata = {
        queue_scope: 'remote_render',
        worker_platform: 'korea_render_pc',
        upload_owner: 'web_admin',
        publish_owner: 'web_admin',
        visibility_control: 'web_admin_pending',
        package_transport: 'google_drive_api',
        job_stage: 'pending',
        asset_file_id: driveFile.id,
        asset_file_name: driveFile.name,
        asset_file_size: driveFile.size,
        asset_md5: (driveFile as any).md5Checksum,
        asset_web_link: driveFile.webViewLink || driveFileLink(driveFile.id),
        source: 'picadiri_local_app',
        std_web_project_id: project.id,
        topic_queue_id: project.topic_queue_id,
        drive_folder_id: folders.projectFolderId,
        drive_folder_link: driveFolderLink(folders.projectFolderId),
        admin_publish_ready: false,
        admin_publish_status: 'render_pending',
    }

    const now = new Date().toISOString()
    const taskId = randomUUID()
    const payload = {
        id: taskId,
        project_id: pseudoProjectId,
        project_name: project.title || `Project ${pseudoProjectId}`,
        email: project.employee_email || 'unknown',
        status: 'pending',
        progress: 0,
        message: 'Google Drive asset package upload complete. Waiting for remote render.',
        render_mode: 'drive_api',
        asset_file_id: driveFile.id,
        asset_file_name: driveFile.name,
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
                drive_folder_id: folders.projectFolderId,
                progress_payload: {
                    ...(project.progress_payload || {}),
                    remote_task_id: taskId,
                    remote_render_queue_id: taskId,
                    remote_render_mode: 'drive_api',
                    remote_asset_file_id: driveFile.id,
                    remote_asset_file_name: driveFile.name,
                    remote_asset_web_link: driveFile.webViewLink || driveFileLink(driveFile.id),
                    remote_render_queue_payload: payload,
                    admin_publish_status: 'render_pending',
                    submitted_to_render_queue_at: now,
                },
                updated_at: now,
            })
            .eq('id', project.id),
    ])

    return row
}
