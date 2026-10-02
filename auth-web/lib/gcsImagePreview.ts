import { createHash } from 'crypto'
import sharp from 'sharp'
import { downloadGcsObject, uploadGcsBuffer } from './gcsStorage'

const pending = new Map<string, Promise<Buffer>>()

export async function readGcsImagePreview(bucket: string, objectPath: string): Promise<Buffer> {
    const path = `previews/std-images/${createHash('sha256').update(`${bucket}:${objectPath}:960-webp-v1`).digest('hex')}.webp`
    const key = `${bucket}:${path}`
    const existing = pending.get(key)
    if (existing) return existing
    const task = (async () => {
        try { return await downloadGcsObject({ bucket, objectPath: path }) }
        catch (error: any) { if (Number(error?.code) !== 404) throw error }
        const original = await downloadGcsObject({ bucket, objectPath })
        const preview = await sharp(original).rotate().resize({ width: 960, height: 960, fit: 'inside', withoutEnlargement: true }).webp({ quality: 75 }).toBuffer()
        await uploadGcsBuffer({ bucket, objectPath: path, buffer: preview, contentType: 'image/webp' })
        return preview
    })()
    pending.set(key, task)
    try { return await task } finally { pending.delete(key) }
}
