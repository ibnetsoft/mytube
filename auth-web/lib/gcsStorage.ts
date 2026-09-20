import { Storage } from '@google-cloud/storage'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

const DEFAULT_BUCKET = 'air-studio-prod'
const DEFAULT_PROJECT_ID = 'air-studio-prod'

export type GcsObjectRef = {
    provider: 'gcs'
    bucket: string
    path: string
}

let cachedConfig: {
    bucketName: string
    projectId: string
    clientEmail: string
    privateKey: string
    loadedAt: number
} | null = null

const CONFIG_TTL_MS = 60_000
let storageClient: Storage | null | undefined

function env(name: string) {
    return String(process.env[name] || '').trim()
}

export async function refreshGcsConfigFromDb(): Promise<void> {
    try {
        const { data, error } = await supabaseAdmin
            .from('global_settings')
            .select('key,value')
            .in('key', [
                'sys_api_gcs_bucket_name',
                'sys_api_gcs_project_id',
                'sys_api_gcs_client_email',
                'sys_api_gcs_private_key',
            ])
        if (!error && data) {
            const map = Object.fromEntries(data.map(r => [r.key, String(r.value || '').trim()]))
            const bucketName = map.sys_api_gcs_bucket_name || env('GCS_BUCKET_NAME') || DEFAULT_BUCKET
            const projectId = map.sys_api_gcs_project_id || env('GCS_PROJECT_ID') || env('GOOGLE_CLOUD_PROJECT') || DEFAULT_PROJECT_ID
            const clientEmail = map.sys_api_gcs_client_email || env('GCS_CLIENT_EMAIL') || env('GOOGLE_CLIENT_EMAIL')
            const rawKey = map.sys_api_gcs_private_key || env('GCS_PRIVATE_KEY') || env('GOOGLE_PRIVATE_KEY')
            const privateKey = rawKey ? rawKey.replace(/\\n/g, '\n') : ''
            cachedConfig = { bucketName, projectId, clientEmail, privateKey, loadedAt: Date.now() }
            storageClient = undefined
        }
    } catch {
        // Keep existing config or fallback to env
    }
}

export async function getGcsConfig() {
    if (!cachedConfig || Date.now() - cachedConfig.loadedAt > CONFIG_TTL_MS) {
        await refreshGcsConfigFromDb()
    }
    if (!cachedConfig) {
        const bucketName = env('GCS_BUCKET_NAME') || DEFAULT_BUCKET
        const projectId = env('GCS_PROJECT_ID') || env('GOOGLE_CLOUD_PROJECT') || DEFAULT_PROJECT_ID
        const clientEmail = env('GCS_CLIENT_EMAIL') || env('GOOGLE_CLIENT_EMAIL')
        const rawKey = env('GCS_PRIVATE_KEY') || env('GOOGLE_PRIVATE_KEY')
        const privateKey = rawKey ? rawKey.replace(/\\n/g, '\n') : ''
        cachedConfig = { bucketName, projectId, clientEmail, privateKey, loadedAt: Date.now() }
    }
    return cachedConfig
}

export function gcsBucketName() {
    return cachedConfig?.bucketName || env('GCS_BUCKET_NAME') || DEFAULT_BUCKET
}

export function gcsProjectId() {
    return cachedConfig?.projectId || env('GCS_PROJECT_ID') || env('GOOGLE_CLOUD_PROJECT') || DEFAULT_PROJECT_ID
}

export function gcsClientEmail() {
    return cachedConfig?.clientEmail || env('GCS_CLIENT_EMAIL') || env('GOOGLE_CLIENT_EMAIL')
}

export function gcsPrivateKey() {
    if (cachedConfig?.privateKey) return cachedConfig.privateKey
    const raw = env('GCS_PRIVATE_KEY') || env('GOOGLE_PRIVATE_KEY')
    return raw ? raw.replace(/\\n/g, '\n') : ''
}

export function isGcsStorageConfigured(): boolean {
    const conf = cachedConfig
    if (conf && conf.bucketName && conf.clientEmail && conf.privateKey) {
        return true
    }
    const bucket = env('GCS_BUCKET_NAME') || DEFAULT_BUCKET
    const email = env('GCS_CLIENT_EMAIL') || env('GOOGLE_CLIENT_EMAIL')
    const key = env('GCS_PRIVATE_KEY') || env('GOOGLE_PRIVATE_KEY')
    return Boolean(bucket && email && key)
}

export async function isGcsConfiguredAsync(): Promise<boolean> {
    const conf = await getGcsConfig()
    return Boolean(conf.bucketName && conf.clientEmail && conf.privateKey)
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
    const conf = cachedConfig || {
        bucketName: gcsBucketName(),
        projectId: gcsProjectId(),
        clientEmail: gcsClientEmail(),
        privateKey: gcsPrivateKey(),
    }
    if (!conf.clientEmail || !conf.privateKey) {
        storageClient = null
        return storageClient
    }
    storageClient = new Storage({
        projectId: conf.projectId,
        credentials: {
            client_email: conf.clientEmail,
            private_key: conf.privateKey,
        },
    })
    return storageClient
}

function getBucket(overrideBucket?: string) {
    const client = getStorageClient()
    if (!client) throw new Error('GCS storage is not configured')
    const bucketName = overrideBucket || gcsBucketName()
    return client.bucket(bucketName)
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
    await getGcsConfig().catch(() => null)
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
    await getGcsConfig().catch(() => null)
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
    data?: Buffer
    buffer?: Buffer
    contentType: string
    bucket?: string
}) {
    const rawData = input.data || input.buffer
    if (!rawData) throw new Error('uploadGcsBuffer: missing data/buffer parameter')
    await getGcsConfig().catch(() => null)
    const bucket = getBucket(input.bucket)
    await bucket.file(input.objectPath).save(rawData, {
        resumable: false,
        contentType: input.contentType,
        metadata: {
            cacheControl: 'private, max-age=86400',
        },
    })
    return {
        provider: 'gcs' as const,
        bucket: input.bucket || gcsBucketName(),
        path: input.objectPath,
    }
}

export async function downloadGcsObject(input: {
    bucket?: string
    objectPath: string
}) {
    await getGcsConfig().catch(() => null)
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

/**
 * 2차 스토리지 아카이빙: Supabase Storage에 성공적으로 저장된 에셋을
 * GCS(Google Cloud Storage)에 복제 보관하고 메타데이터를 갱신합니다.
 * GCS가 미설정이거나 실패하더라도 1차 Supabase 에셋은 온전히 유지됩니다.
 */
export async function archiveSupabaseAssetToGcs(project: any, asset: any) {
    if (!asset || !asset.id) return asset
    await getGcsConfig().catch(() => null)
    if (!isGcsStorageConfigured()) {
        return asset
    }

    const storageBucket = String(asset?.metadata?.storage_bucket || 'content-assets').trim()
    const storagePath = String(asset?.metadata?.storage_path || '').trim().replace(/^\/+/, '')
    if (!storagePath) return asset

    try {
        const { data: fileBlob, error: downloadError } = await supabaseAdmin.storage
            .from(storageBucket)
            .download(storagePath)

        if (downloadError || !fileBlob) {
            console.warn('[archiveSupabaseAssetToGcs] Failed to download from Supabase Storage:', downloadError?.message)
            return asset
        }

        const buffer = Buffer.from(await fileBlob.arrayBuffer())
        const stored = await uploadGcsBuffer({
            objectPath: storagePath,
            data: buffer,
            contentType: asset.mime_type || 'application/octet-stream',
        })

        const currentMetadata = asset.metadata || {}
        const nextMetadata = {
            ...currentMetadata,
            gcs_bucket: stored.bucket,
            gcs_path: stored.path,
            upload_mode: 'browser_supabase_then_gcs',
        }

        const { data: updatedAsset, error: updateError } = await supabaseAdmin
            .from('std_project_assets')
            .update({
                metadata: nextMetadata,
                updated_at: new Date().toISOString(),
            })
            .eq('id', asset.id)
            .select('*')
            .single()

        if (updateError) {
            console.warn('[archiveSupabaseAssetToGcs] Asset metadata update failed:', updateError.message)
            return asset
        }
        return updatedAsset || asset
    } catch (e: any) {
        console.warn('[archiveSupabaseAssetToGcs] GCS archive failed; keeping Supabase asset as primary:', e?.message || e)
        return asset
    }
}

// Module-load cache pre-fetch
if (typeof window === 'undefined') {
    refreshGcsConfigFromDb().catch(() => {})
}
