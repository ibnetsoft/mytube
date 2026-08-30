// Server-side Google Drive helper for auth-web admin routes.
//
// This reuses the exact same refresh_token -> access_token exchange as
// app/api/desktop-drive-token/route.ts (the "Drive central bridge" - see
// worknote/AIR-drive-central-bridge.md). That endpoint exists so untrusted
// client machines never hold the long-lived refresh_token; admin API routes
// run in the same trusted server process as that endpoint, so they can call
// this exchange directly in-process instead of round-tripping over HTTP.
//
// Only file content (get/update/create) is implemented here - just enough
// for the render-queue thumbnail/description editor. This does NOT replace
// services/google_drive_service.py (Python) which remains the primary Drive
// integration for rendering/uploading.

import { getGoogleDriveAccessToken } from '@/lib/googleDriveConfig'

export async function getDriveAccessToken(): Promise<string> {
    return (await getGoogleDriveAccessToken()).accessToken
}

export async function getDriveFileJson(fileId: string): Promise<any> {
    const token = await getDriveAccessToken()
    const res = await fetch(`https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`, {
        headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
        throw new Error(`drive_get_failed: HTTP ${res.status}`)
    }
    const text = await res.text()
    return JSON.parse(text)
}

export async function updateDriveFileJson(fileId: string, data: any): Promise<void> {
    const token = await getDriveAccessToken()
    const res = await fetch(`https://www.googleapis.com/upload/drive/v3/files/${fileId}?uploadType=media`, {
        method: 'PATCH',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json; charset=UTF-8',
        },
        body: JSON.stringify(data, null, 2),
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_update_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
}

export async function createDriveJsonFile(folderId: string, filename: string, data: any): Promise<string> {
    const token = await getDriveAccessToken()
    const boundary = 'air_studio_boundary_' + Math.random().toString(36).slice(2)
    const metadata = { name: filename, parents: [folderId], mimeType: 'application/json' }
    const body =
        `--${boundary}\r\n` +
        `Content-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(metadata)}\r\n` +
        `--${boundary}\r\n` +
        `Content-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(data, null, 2)}\r\n` +
        `--${boundary}--`

    const res = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': `multipart/related; boundary=${boundary}`,
        },
        body,
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_create_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
    const json = await res.json()
    return json.id as string
}

export async function updateDriveFileMedia(fileId: string, bytes: ArrayBuffer, mimeType: string): Promise<void> {
    const token = await getDriveAccessToken()
    const res = await fetch(`https://www.googleapis.com/upload/drive/v3/files/${fileId}?uploadType=media`, {
        method: 'PATCH',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': mimeType,
        },
        body: bytes,
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_thumbnail_update_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
}

export async function createDriveMediaFile(folderId: string, filename: string, bytes: ArrayBuffer, mimeType: string): Promise<string> {
    const token = await getDriveAccessToken()
    const boundary = 'air_studio_boundary_' + Math.random().toString(36).slice(2)
    const metadata = { name: filename, parents: [folderId], mimeType }
    const head =
        `--${boundary}\r\n` +
        `Content-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(metadata)}\r\n` +
        `--${boundary}\r\n` +
        `Content-Type: ${mimeType}\r\n\r\n`
    const tail = `\r\n--${boundary}--`

    const body = Buffer.concat([Buffer.from(head, 'utf-8'), Buffer.from(bytes), Buffer.from(tail, 'utf-8')])

    const res = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': `multipart/related; boundary=${boundary}`,
        },
        body,
    })
    if (!res.ok) {
        const detail = await res.text()
        throw new Error(`drive_thumbnail_create_failed: HTTP ${res.status} ${detail.slice(0, 200)}`)
    }
    const json = await res.json()
    return json.id as string
}
