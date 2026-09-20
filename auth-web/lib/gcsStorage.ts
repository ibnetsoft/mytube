import { Storage } from '@google-cloud/storage'

const DEFAULT_BUCKET = 'air-studio-prod'
const DEFAULT_PROJECT_ID = 'air-studio-prod'

let storageClient: Storage | null | undefined

export type GcsObjectRef = {
    provider: 'gcs'
    bucket: string
    path: string
}

function env(name: string) {
    return String(process.env[name] || '').trim()
}

function gcsBucketName() {
    return env('GCS_BUCKET_NAME') || DEFAULT_BUCKET
}

function gcsProjectId() {
    return env('GCS_PROJECT_ID') || env('GOOGLE_CLOUD_PROJECT') || DEFAULT_PROJECT_ID
}

function gcsClientEmail() {
    return env('GCS_CLIENT_EMAIL') || env('GOOGLE_CLIENT_EMAIL')
}

function gcsPrivateKey() {
    const raw = env('GCS_PRIVATE_KEY') || env('GOOGLE_PRIVATE_KEY')
    return raw ? raw.replace(/\\n/g, '\n') : ''
}

export function isGcsStorageConfigured() {
    return Boolean(gcsBucketName() && (gcsClientEmail() && gcsPrivateKey()))
}

export function sanitizeGcsObjectName(value: string, fallback = 'asset') {
    const safe = String(value || '')
        .replace(/[\\/:*?"<>|#%{}~&]/g, '_')
        .replace(/\s+/g, '_')
        .replace(/_+/g, '_')
        .trim()
    return (safe || fallback).slice(0, 180)
}

function getStorageClient() {
    if (storageClient !== undefined) return storageClient
    if (!isGcsStorageConfigured()) {
        storageClient = null
        return storageClient
    }
    storageClient = new Storage({
        projectId: gcsProjectId(),
        credentials: {
            client_email: gcsClientEmail(),
            private_key: gcsPrivateKey(),
        },
    })
    return storageClient
}

function getBucket() {
    const client = getStorageClient()
    if (!client) throw new Error('GCS storage is not configured')
    return client.bucket(gcsBucketName())
}

export function buildStdGcsObjectPath(input: {
    projectId: string
    sceneNumber?: number | null
    fileName: string
}) {
    return [
        'std-projects',
        input.projectId,
        input.sceneNumber == null ? 'project-assets' : `scenes/${Math.floor(input.sceneNumber)}`,
        `${Date.now()}-${sanitizeGcsObjectName(input.fileName)}`,
    ].join('/')
}

export async function createGcsSignedUploadUrl(input: {
    objectPath: string
    contentType: string
    expiresInMinutes?: number
}) {
    const file = getBucket().file(input.objectPath)
    const expiresAt = Date.now() + (input.expiresInMinutes || 30) * 60_000
    const [signedUrl] = await file.getSignedUrl({
        version: 'v4',
        action: 'write',
        expires: expiresAt,
        contentType: input.contentType,
    })
    return {
        signedUrl,
        bucket: gcsBucketName(),
        path: input.objectPath,
        expiresAt: new Date(expiresAt).toISOString(),
    }
}

export async function createGcsSignedReadUrl(input: {
    bucket?: string
    objectPath: string
    expiresInMinutes?: number
}) {
    const bucket = input.bucket ? getStorageClient()?.bucket(input.bucket) : getBucket()
    if (!bucket) throw new Error('GCS storage is not configured')
    const expiresAt = Date.now() + (input.expiresInMinutes || 30) * 60_000
    const [signedUrl] = await bucket.file(input.objectPath).getSignedUrl({
        version: 'v4',
        action: 'read',
        expires: expiresAt,
    })
    return signedUrl
}

export async function uploadGcsBuffer(input: {
    objectPath: string
    data: Buffer
    contentType: string
}) {
    await getBucket().file(input.objectPath).save(input.data, {
        resumable: false,
        contentType: input.contentType,
        metadata: {
            cacheControl: 'private, max-age=86400',
        },
    })
    return {
        provider: 'gcs' as const,
        bucket: gcsBucketName(),
        path: input.objectPath,
    }
}

export async function downloadGcsObject(input: {
    bucket?: string
    objectPath: string
}) {
    const bucket = input.bucket ? getStorageClient()?.bucket(input.bucket) : getBucket()
    if (!bucket) throw new Error('GCS storage is not configured')
    const [data] = await bucket.file(input.objectPath).download()
    return data
}

export async function downloadGcsObjectViaSignedUrl(input: {
    bucket?: string
    objectPath: string
    range?: string | null
}) {
    const signedUrl = await createGcsSignedReadUrl({
        bucket: input.bucket,
        objectPath: input.objectPath,
        expiresInMinutes: 10,
    })
    const res = await fetch(signedUrl, {
        headers: input.range ? { Range: input.range } : {},
        cache: 'no-store',
    })
    if (!res.ok) {
        const detail = await res.text().catch(() => '')
        throw new Error(`gcs_download_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
    return {
        buffer: Buffer.from(await res.arrayBuffer()),
        status: res.status,
        contentRange: res.headers.get('content-range'),
        contentLength: res.headers.get('content-length'),
        contentType: res.headers.get('content-type'),
    }
}

export function gcsObjectRef(bucket: string, objectPath: string): GcsObjectRef {
    return {
        provider: 'gcs',
        bucket: bucket || gcsBucketName(),
        path: objectPath.replace(/^\/+/, ''),
    }
}
