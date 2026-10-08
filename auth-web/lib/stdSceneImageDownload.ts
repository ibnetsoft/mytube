import sharp from 'sharp'
import { downloadGcsObject } from './gcsStorage'
import { sceneImageUrl } from './stdSceneMediaUrl'

/** Download the original, not the reduced preview or an unauthenticated self-fetch. */
export async function readSceneImage(req: Request, scene: any, payloadScene?: any) {
    const imageUrl = sceneImageUrl(scene) || sceneImageUrl(payloadScene)
    if (!imageUrl) throw new Error('Scene image not found')
    const requestUrl = new URL(req.url)
    const url = new URL(imageUrl, requestUrl.origin)
    let buffer: Buffer
    if (url.origin === requestUrl.origin && url.pathname === '/api/std/assets/gcs-file') {
        const bucket = String(url.searchParams.get('bucket') || '').trim()
        const objectPath = String(url.searchParams.get('path') || '').trim().replace(/^\/+/, '')
        if (!bucket || !objectPath || objectPath.includes('..')) throw new Error('Invalid scene image storage path')
        buffer = await downloadGcsObject({ bucket, objectPath })
    } else {
        // Cookies/tokens may be sent only to this application's own asset routes.
        const headers = new Headers()
        if (url.origin === requestUrl.origin) {
            for (const name of ['authorization', 'cookie', 'x-impersonate-email']) {
                const value = req.headers.get(name)
                if (value) headers.set(name, value)
            }
        }
        const response = await fetch(url, { headers, cache: 'no-store' })
        if (!response.ok) throw new Error(`Scene image fetch failed (${response.status})`)
        buffer = Buffer.from(await response.arrayBuffer())
    }
    // Determine the filename and MIME from the bytes, never from a misleading URL/header.
    const metadata = await sharp(buffer, { failOn: 'error' }).metadata()
    const formats: Record<string, { extension: string, contentType: string }> = {
        png: { extension: 'png', contentType: 'image/png' },
        jpeg: { extension: 'jpg', contentType: 'image/jpeg' },
        webp: { extension: 'webp', contentType: 'image/webp' },
        gif: { extension: 'gif', contentType: 'image/gif' },
        heif: { extension: 'avif', contentType: 'image/avif' },
        tiff: { extension: 'tiff', contentType: 'image/tiff' },
    }
    const format = formats[metadata.format || '']
    if (!format || !metadata.width || !metadata.height) throw new Error('Invalid scene image')
    return { buffer, ...format }
}
