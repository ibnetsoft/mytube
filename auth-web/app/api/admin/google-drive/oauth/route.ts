import { NextResponse } from 'next/server'
import { createHmac, randomBytes } from 'crypto'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'
import { getGoogleDriveConfig } from '@/lib/googleDriveConfig'

export const dynamic = 'force-dynamic'

const DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive'

function createState(clientSecret: string): string {
    const nonce = randomBytes(32).toString('hex')
    const issuedAt = Date.now().toString()
    const payload = `${nonce}.${issuedAt}`
    const signature = createHmac('sha256', clientSecret).update(payload).digest('hex')
    return `${payload}.${signature}`
}

export async function POST(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    const config = await getGoogleDriveConfig()
    if (!config.clientId || !config.clientSecret) {
        return NextResponse.json({ error: 'Google Drive OAuth Client ID와 Client Secret을 먼저 저장해주세요.' }, { status: 409 })
    }

    const origin = new URL(req.url).origin
    const redirectUri = `${origin}/api/admin/google-drive/oauth/callback`
    const state = createState(config.clientSecret)
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

    return NextResponse.json({ authorization_url: authorizationUrl.toString(), redirect_uri: redirectUri })
}
