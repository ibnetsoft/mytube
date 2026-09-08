import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { getGoogleDriveAccessToken } from '@/lib/googleDriveConfig'

export const dynamic = 'force-dynamic'

const SFX_LIBRARY_FOLDER_ID = '1xu6GBDh8F8iF5wsSiqgzeM6YG2iB-Utq'

async function listFolder(accessToken: string, folderId: string, prefix = ''): Promise<any[]> {
    const query = encodeURIComponent(`'${folderId}' in parents and trashed = false`)
    const response = await fetch(`https://www.googleapis.com/drive/v3/files?q=${query}&fields=files(id,name,mimeType,parents)&pageSize=1000`, {
        headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store',
    })
    if (!response.ok) throw new Error(`Drive library list failed (${response.status})`)
    const payload = await response.json()
    const items: any[] = []
    for (const file of payload.files || []) {
        if (file.mimeType === 'application/vnd.google-apps.folder') {
            items.push(...await listFolder(accessToken, file.id, `${prefix}${file.name}/`))
        } else if (String(file.mimeType || '').startsWith('audio/')) {
            items.push({ drive_file_id: file.id, file_name: file.name, title: file.name.replace(/\.[^.]+$/, ''), category: prefix.split('/').filter(Boolean)[0] || 'library' })
        }
    }
    return items
}

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    try {
        const { accessToken } = await getGoogleDriveAccessToken()
        const items = await listFolder(accessToken, SFX_LIBRARY_FOLDER_ID)
        return NextResponse.json({ items: items.sort((a, b) => a.title.localeCompare(b.title)) })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'SFX library load failed' }, { status: 500 })
    }
}
