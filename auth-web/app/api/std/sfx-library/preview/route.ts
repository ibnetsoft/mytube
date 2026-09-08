import { downloadStdDriveFile } from '@/lib/stdGoogleDrive'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    const fileId = new URL(req.url).searchParams.get('fileId') || ''
    if (!fileId) return new Response('fileId is required', { status: 400 })
    try {
        const audio = await downloadStdDriveFile(fileId)
        return new Response(new Uint8Array(audio), { headers: { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'private, max-age=3600' } })
    } catch {
        return new Response('SFX file not found', { status: 404 })
    }
}
