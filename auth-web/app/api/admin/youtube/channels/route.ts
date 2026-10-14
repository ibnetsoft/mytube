import { NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../../_auth'
import { startYoutubeChannelOAuth, youtubeConnectedChannels } from '@/lib/stdYoutubeChannelOAuth'
export const dynamic = 'force-dynamic'
export async function GET(req: Request) {
    const auth = await requireSuperAdmin(req)
    if (isAuthResponse(auth)) return auth
    return NextResponse.json({ success: true, channels: await youtubeConnectedChannels() })
}
export async function POST(req: Request) {
    const auth = await requireSuperAdmin(req)
    if (isAuthResponse(auth)) return auth
    const body = await req.json()
    const categoryId = Number(body.category_id), channelId = Number(body.local_channel_id || categoryId)
    if (!Number.isSafeInteger(categoryId) || categoryId <= 0 || !Number.isSafeInteger(channelId) || channelId <= 0)
        return NextResponse.json({ error: 'Invalid channel/category' }, { status: 400 })
    try { return NextResponse.json({ authorization_url: await startYoutubeChannelOAuth(new URL(req.url).origin, categoryId, channelId) }) }
    catch { return NextResponse.json({ error: 'YouTube 인증 설정을 확인해 주세요.' }, { status: 409 }) }
}
