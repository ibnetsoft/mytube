import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { getGoogleDriveAccessToken } from '@/lib/googleDriveConfig'

export const dynamic = 'force-dynamic'

const SFX_LIBRARY_FOLDER_NAME = 'SFX'
// Shared SFX folder created in the production Drive account. An environment
// override keeps the library movable without changing application code.
const SFX_LIBRARY_FOLDER_ID = process.env.GOOGLE_DRIVE_SFX_LIBRARY_FOLDER_ID || '1xu6GBDh8F8iF5wsSiggzeM6YG2iB-Utq'

async function findSfxLibraryFolder(accessToken: string): Promise<string> {
    const directResponse = await fetch(`https://www.googleapis.com/drive/v3/files/${SFX_LIBRARY_FOLDER_ID}?fields=id,name,mimeType`, {
        headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store',
    })
    if (directResponse.ok) {
        const directFolder = await directResponse.json()
        if (directFolder.mimeType === 'application/vnd.google-apps.folder') return String(directFolder.id)
    }

    const params = new URLSearchParams({
        q: `'root' in parents and name = '${SFX_LIBRARY_FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`,
        fields: 'files(id,name)',
        pageSize: '10',
        spaces: 'drive',
        corpora: 'user',
        supportsAllDrives: 'true',
        includeItemsFromAllDrives: 'true',
    })
    const response = await fetch(`https://www.googleapis.com/drive/v3/files?${params}`, {
        headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store',
    })
    if (!response.ok) throw new Error(`Drive SFX folder lookup failed (${response.status})`)
    const payload = await response.json()
    const folderId = String(payload.files?.[0]?.id || '')
    if (!folderId) throw new Error('내 드라이브 최상단에서 SFX 폴더를 찾지 못했습니다.')
    return folderId
}

async function listFolder(accessToken: string, folderId: string, prefix = ''): Promise<any[]> {
    const params = new URLSearchParams({
        q: `'${folderId}' in parents and trashed = false`,
        fields: 'files(id,name,mimeType,parents)',
        pageSize: '1000',
        spaces: 'drive',
        supportsAllDrives: 'true',
        includeItemsFromAllDrives: 'true',
    })
    const response = await fetch(`https://www.googleapis.com/drive/v3/files?${params}`, {
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
        const folderId = await findSfxLibraryFolder(accessToken)
        const items = await listFolder(accessToken, folderId)
        return NextResponse.json({ items: items.sort((a, b) => a.title.localeCompare(b.title)) })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'SFX library load failed' }, { status: 500 })
    }
}
