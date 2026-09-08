import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { getGoogleDriveConfig } from '@/lib/googleDriveConfig'

export const dynamic = 'force-dynamic'

const STATE_COOKIE = 'admin_drive_oauth_state'

function redirect(req: Request, result: string): NextResponse {
    const destination = new URL('/dashboard', req.url)
    destination.searchParams.set('drive_oauth', result)
    return NextResponse.redirect(destination)
}

function readPendingStates(cookieHeader: string | null): string[] {
    const raw = cookieHeader
        ?.split(';')
        .map(value => value.trim().split('='))
        .find(([name]) => name === STATE_COOKIE)
        ?.slice(1)
        .join('=') || ''
    if (!raw) return []

    try {
        const parsed = JSON.parse(decodeURIComponent(raw))
        return Array.isArray(parsed) ? parsed.filter(value => typeof value === 'string') : []
    } catch {
        // Accept a state created by older deployments until it naturally expires.
        return [decodeURIComponent(raw)]
    }
}

export async function GET(req: Request) {
    const url = new URL(req.url)
    const receivedState = String(url.searchParams.get('state') || '')
    const pendingStates = readPendingStates(req.headers.get('cookie'))

    if (!receivedState || !pendingStates.includes(receivedState)) {
        return redirect(req, 'state_mismatch')
    }

    const providerError = url.searchParams.get('error')
    const code = url.searchParams.get('code')
    if (providerError || !code) return redirect(req, providerError || 'missing_code')

    try {
        const config = await getGoogleDriveConfig()
        if (!config.clientId || !config.clientSecret) return redirect(req, 'client_not_configured')

        const redirectUri = `${url.origin}/api/admin/google-drive/oauth/callback`
        const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({
                code,
                client_id: config.clientId,
                client_secret: config.clientSecret,
                redirect_uri: redirectUri,
                grant_type: 'authorization_code',
            }),
            cache: 'no-store',
        })
        const tokenPayload = await tokenResponse.json().catch(() => ({}))
        const refreshToken = String(tokenPayload?.refresh_token || '')
        if (!tokenResponse.ok || !refreshToken) return redirect(req, 'token_exchange_failed')

        const { error } = await supabaseAdmin
            .from('global_settings')
            .upsert({ key: 'sys_api_google_drive_refresh_token', value: refreshToken }, { onConflict: 'key' })
        if (error) throw error

        const response = redirect(req, 'connected')
        response.cookies.set(STATE_COOKIE, '', { httpOnly: true, sameSite: 'lax', path: '/api/admin/google-drive/oauth', maxAge: 0 })
        return response
    } catch {
        return redirect(req, 'save_failed')
    }
}
