import { getGoogleDriveAccessToken, getGoogleDriveConfig } from './googleDriveConfig'

const DRIVE_FOLDER_MIME = 'application/vnd.google-apps.folder'

type DriveFolderSet = {
    projectFolderId: string
    imagesFolderId: string
    videosFolderId: string
    originalsFolderId: string
    audioFolderId: string
}

type UploadSessionInput = {
    folderId: string
    fileName: string
    mimeType: string
    fileSize?: number | null
}

type DriveFileMetadata = {
    id: string
    name: string
    mimeType?: string
    size?: string
    parents?: string[]
    webViewLink?: string
    thumbnailLink?: string
}

const STD_FOLDER_CACHE_TTL_MS = 5 * 60_000
const stdProjectFolderCache = new Map<string, { expiresAt: number; folders: DriveFolderSet }>()

export async function resolveDriveRootFolderId(): Promise<string> {
    return (await getGoogleDriveConfig()).rootFolderId
}

export function sanitizeDriveName(value: string, fallback = 'untitled'): string {
    const cleaned = String(value || '')
        .replace(/[\\/:*?"<>|#%{}~&]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
    return (cleaned || fallback).slice(0, 140)
}

async function getStdDriveAccessToken(): Promise<string> {
    return (await getGoogleDriveAccessToken()).accessToken
}

async function driveJson<T>(url: string, init: RequestInit = {}): Promise<T> {
    const token = await getStdDriveAccessToken()
    const res = await fetch(url, {
        ...init,
        headers: {
            Authorization: `Bearer ${token}`,
            ...(init.headers || {}),
        },
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_request_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
    return await res.json() as T
}

function escapeDriveQuery(value: string): string {
    return value.replace(/\\/g, '\\\\').replace(/'/g, "\\'")
}

async function findFolder(parentId: string, name: string): Promise<string | null> {
    const query = [
        `'${escapeDriveQuery(parentId)}' in parents`,
        `name = '${escapeDriveQuery(name)}'`,
        `mimeType = '${DRIVE_FOLDER_MIME}'`,
        'trashed = false',
    ].join(' and ')
    const params = new URLSearchParams({
        q: query,
        fields: 'files(id,name)',
        pageSize: '1',
        supportsAllDrives: 'true',
        includeItemsFromAllDrives: 'true',
    })
    const payload = await driveJson<{ files?: Array<{ id: string }> }>(`https://www.googleapis.com/drive/v3/files?${params}`)
    return payload.files?.[0]?.id || null
}

async function createFolder(parentId: string, name: string): Promise<string> {
    const payload = await driveJson<{ id: string }>('https://www.googleapis.com/drive/v3/files?fields=id', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=UTF-8' },
        body: JSON.stringify({
            name,
            mimeType: DRIVE_FOLDER_MIME,
            parents: [parentId],
        }),
    })
    return payload.id
}

export async function ensureDriveFolder(parentId: string, name: string): Promise<string> {
    return await findFolder(parentId, name) || await createFolder(parentId, name)
}

export async function ensureStdProjectDriveFolders(project: any): Promise<DriveFolderSet> {
    const rootFolderId = await resolveDriveRootFolderId()
    if (!rootFolderId) throw new Error('drive_root_folder_not_configured')
    const cacheKey = `${String(project?.id || '')}:${rootFolderId}`
    const cached = stdProjectFolderCache.get(cacheKey)
    if (cached && cached.expiresAt > Date.now()) return cached.folders
    const projectPayload = project?.progress_payload || {}
    const existing = projectPayload?.std_drive?.folder_ids || {}
    const existingProjectFolderId = String(existing.project || project?.drive_folder_id || '').trim()

    if (existingProjectFolderId && existing.images && existing.videos && existing.originals) {
        try {
            const audioFolderId = existing.audio || await ensureDriveFolder(existingProjectFolderId, '04_audio')
            const [projectMeta, imagesMeta, videosMeta, originalsMeta, audioMeta] = await Promise.all([
                getStdDriveFileMetadata(existingProjectFolderId),
                getStdDriveFileMetadata(existing.images),
                getStdDriveFileMetadata(existing.videos),
                getStdDriveFileMetadata(existing.originals),
                getStdDriveFileMetadata(audioFolderId),
            ])
            const projectIsInCurrentRoot = projectMeta.mimeType === DRIVE_FOLDER_MIME
                && projectMeta.parents?.includes(rootFolderId)
            const childFoldersAreCurrent = [imagesMeta, videosMeta, originalsMeta, audioMeta].every(meta =>
                meta.mimeType === DRIVE_FOLDER_MIME && meta.parents?.includes(existingProjectFolderId)
            )
            if (projectIsInCurrentRoot && childFoldersAreCurrent) {
                const folders = {
                    projectFolderId: existingProjectFolderId,
                    imagesFolderId: existing.images,
                    videosFolderId: existing.videos,
                    originalsFolderId: existing.originals,
                    audioFolderId,
                }
                stdProjectFolderCache.set(cacheKey, {
                    expiresAt: Date.now() + STD_FOLDER_CACHE_TTL_MS,
                    folders,
                })
                return folders
            }
        } catch {
            // Missing or inaccessible legacy folders are recreated below under the active root.
        }
    }

    const title = sanitizeDriveName(project?.title || project?.id, 'std-project')
    const projectFolderName = sanitizeDriveName(`STD_${String(project?.id || '').slice(0, 8)}_${title}`)
    const projectFolderId = await ensureDriveFolder(rootFolderId, projectFolderName)
    const imagesFolderId = await ensureDriveFolder(projectFolderId, '01_images')
    const videosFolderId = await ensureDriveFolder(projectFolderId, '02_videos')
    const originalsFolderId = await ensureDriveFolder(projectFolderId, '03_originals')
    const audioFolderId = await ensureDriveFolder(projectFolderId, '04_audio')

    const folders = { projectFolderId, imagesFolderId, videosFolderId, originalsFolderId, audioFolderId }
    stdProjectFolderCache.set(cacheKey, {
        expiresAt: Date.now() + STD_FOLDER_CACHE_TTL_MS,
        folders,
    })
    return folders
}

export function folderForAssetType(folders: DriveFolderSet, assetType: string): string {
    if (assetType === 'image' || assetType === 'thumbnail') return folders.imagesFolderId
    if (assetType === 'video') return folders.videosFolderId
    if (assetType === 'audio' || assetType === 'bgm' || assetType === 'sfx') return folders.audioFolderId
    return folders.originalsFolderId
}

export async function createStdDriveUploadSession(input: UploadSessionInput): Promise<string> {
    const token = await getStdDriveAccessToken()
    const headers: Record<string, string> = {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Upload-Content-Type': input.mimeType,
    }
    if (input.fileSize && Number.isFinite(input.fileSize)) {
        headers['X-Upload-Content-Length'] = String(input.fileSize)
    }

    const res = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name,mimeType,size,parents,webViewLink,thumbnailLink', {
        method: 'POST',
        headers,
        body: JSON.stringify({
            name: sanitizeDriveName(input.fileName),
            parents: [input.folderId],
            mimeType: input.mimeType,
        }),
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_upload_session_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
    const location = res.headers.get('location')
    if (!location) throw new Error('drive_upload_session_missing_location')
    return location
}

export async function getStdDriveFileMetadata(fileId: string): Promise<DriveFileMetadata> {
    const encoded = encodeURIComponent(fileId)
    return await driveJson<DriveFileMetadata>(
        `https://www.googleapis.com/drive/v3/files/${encoded}?fields=id,name,mimeType,size,parents,webViewLink,thumbnailLink&supportsAllDrives=true`
    )
}

export async function downloadStdDriveFile(fileId: string): Promise<Buffer> {
    const encoded = encodeURIComponent(fileId)
    let lastError = 'drive_download_failed'
    for (let attempt = 0; attempt < 2; attempt += 1) {
        const token = await getStdDriveAccessToken()
        const res = await fetch(`https://www.googleapis.com/drive/v3/files/${encoded}?alt=media&supportsAllDrives=true`, {
            headers: { Authorization: `Bearer ${token}` },
            cache: 'no-store',
        })
        if (res.ok) return Buffer.from(await res.arrayBuffer())

        const detail = await res.text()
        lastError = `drive_download_failed: HTTP ${res.status} ${detail.slice(0, 200)}`
        if (res.status !== 401) break
    }
    throw new Error(lastError)
}

export async function uploadStdDriveBuffer(
    folderId: string,
    fileName: string,
    data: Buffer,
    mimeType: string,
    description?: string
): Promise<DriveFileMetadata> {
    const token = await getStdDriveAccessToken()
    const boundary = 'air_std_web_boundary_' + Math.random().toString(36).slice(2)
    const metadata: Record<string, any> = {
        name: sanitizeDriveName(fileName, 'remote_render_pkg.zip'),
        parents: [folderId],
        mimeType,
    }
    if (description) metadata.description = description

    const prefix = Buffer.from(
        `--${boundary}\r\n` +
        `Content-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(metadata)}\r\n` +
        `--${boundary}\r\n` +
        `Content-Type: ${mimeType}\r\n\r\n`,
        'utf8'
    )
    const suffix = Buffer.from(`\r\n--${boundary}--`, 'utf8')

    const res = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,mimeType,size,parents,webViewLink,thumbnailLink,md5Checksum', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': `multipart/related; boundary=${boundary}`,
        },
        body: Buffer.concat([prefix, data, suffix]),
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_buffer_upload_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
    return await res.json() as DriveFileMetadata
}

export async function createStdDriveJsonFile(folderId: string, fileName: string, data: any): Promise<DriveFileMetadata> {
    const token = await getStdDriveAccessToken()
    const boundary = 'air_std_web_boundary_' + Math.random().toString(36).slice(2)
    const metadata = {
        name: sanitizeDriveName(fileName, 'manifest.json'),
        parents: [folderId],
        mimeType: 'application/json',
    }
    const body =
        `--${boundary}\r\n` +
        `Content-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(metadata)}\r\n` +
        `--${boundary}\r\n` +
        `Content-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(data, null, 2)}\r\n` +
        `--${boundary}--`

    const res = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,mimeType,size,parents,webViewLink,thumbnailLink', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': `multipart/related; boundary=${boundary}`,
        },
        body,
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_manifest_create_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
    return await res.json() as DriveFileMetadata
}

export function driveFileLink(fileId: string): string {
    return `https://drive.google.com/file/d/${encodeURIComponent(fileId)}/view`
}

export function driveFolderLink(folderId: string): string {
    return `https://drive.google.com/drive/folders/${encodeURIComponent(folderId)}`
}
