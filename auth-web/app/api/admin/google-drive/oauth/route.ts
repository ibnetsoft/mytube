import { NextResponse } from 'next/server'
import { randomBytes } from 'crypto'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'
import { getGoogleDriveConfig } from '@/lib/googleDriveConfig'

export const dynamic = 'force-dynamic'

const STATE_COOKIE = 'admin_drive_oauth_state'
const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive'

export async function POST(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    const config = await getGoogleDriveConfig()
    if (!config.clientId || !config.clientSecret) {
        return NextResponse.json({ error: 'Google Drive OAuth Client ID와 Client Secret을 먼저 저장해주세요.' }, { status: 409 })
    }

    const origin = new URL(req.url).origin
    const redirectUri = `${origin}/api/admin/google-drive/oauth/callback`
    const state = randomBytes(32).toString('hex')
    const authorizationUrl = new URL('https://accounts.google.com/o/oauth2/v2/auth')
    authorizationUrl.search = new URLSearchParams({
        client_id: config.clientId,
        redirect_uri: redirectUri,
        response_type: 'code',
        scope: DRIVE_SCOPE,
        access_type: 'offline',
        prompt: 'consent',
        state,
    }).toString()

    const response = NextResponse.json({ authorization_url: authorizationUrl.toString(), redirect_uri: redirectUri })
    response.cookies.set(STATE_COOKIE, state, {
        httpOnly: true,
        sameSite: 'lax',
        secure: origin.startsWith('https://'),
        path: '/api/admin/google-drive/oauth',
        maxAge: 10 * 60,
    })
    return response
}
