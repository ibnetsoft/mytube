import { NextResponse } from 'next/server'
import { createHmac, timingSafeEqual } from 'crypto'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { getGoogleDriveConfig } from '@/lib/googleDriveConfig'

export const dynamic = 'force-dynamic'

function redirect(req: Request, result: string): NextResponse {
    const destination = new URL('/dashboard', req.url)
    destination.searchParams.set('drive_oauth', result)
    return NextResponse.redirect(destination)
}

function hasValidState(state: string, clientSecret: string): boolean {
    const [nonce, issuedAt, signature, ...remainder] = state.split('.')
    const issuedAtMs = Number(issuedAt)
    if (
        remainder.length
        || !/^[a-f0-9]{64}$/i.test(nonce || '')
        || !/^\d{13}$/.test(issuedAt || '')
        || !/^[a-f0-9]{64}$/i.test(signature || '')
        || !Number.isFinite(issuedAtMs)
        || issuedAtMs > Date.now()
        || Date.now() - issuedAtMs > 10 * 60 * 1000
    ) return false

    const expected = createHmac('sha256', clientSecret).update(`${nonce}.${issuedAt}`).digest('hex')
    return timingSafeEqual(Buffer.from(signature, 'hex'), Buffer.from(expected, 'hex'))
}

export async function GET(req: Request) {
    const url = new URL(req.url)
    const receivedState = String(url.searchParams.get('state') || '')
    const config = await getGoogleDriveConfig()
    if (!config.clientId || !config.clientSecret) return redirect(req, 'client_not_configured')

    if (!hasValidState(receivedState, config.clientSecret)) {
        return redirect(req, 'state_mismatch')
    }

    const providerError = url.searchParams.get('error')
    const code = url.searchParams.get('code')
    if (providerError || !code) return redirect(req, providerError || 'missing_code')

    try {
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

        return redirect(req, 'connected')
    } catch {
        return redirect(req, 'save_failed')
    }
}
