import { NextResponse } from 'next/server'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0227E/Drive-bridge] Central holder of the Google Drive/YouTube OAuth
// refresh token, so no user-app install (potentially hundreds of unmanaged
// machines) or the render PC ever needs a local token.pickle file. Same
// incident class as AIR-0225B's SUPABASE_SERVICE_ROLE_KEY leak - a long-lived,
// powerful credential must not be distributed to client machines.
//
// This endpoint does NOT proxy Drive uploads/downloads itself (large video
// files would blow past serverless body-size/timeout limits). It only
// exchanges the server-side-only refresh_token for a short-lived
// (~1 hour), narrowly-scoped (drive.file) access_token, which the caller then
// uses to talk to Google's Drive API directly. Leaking that access_token is
// far less dangerous than leaking the refresh_token: it expires in ~1 hour,
// can't mint further tokens, and drive.file already restricts it to files the
// app itself created.
//
// Two caller classes, two auth paths:
//   - user-app (many, less-trusted machines): email + session_token, same
//     HMAC session mechanism as desktop-topics-bridge.
//   - render worker (single, company-controlled machine): already holds
//     SUPABASE_SERVICE_ROLE_KEY locally for its own Supabase polling. Rather
//     than comparing it against a second copy of the same secret stored in
//     this server's own env (which can silently drift - e.g. one copy gets
//     rotated and not the other), the presented key is verified LIVE against
//     Supabase's Auth Admin API, which only a genuine service_role key can
//     call. If it works there, it's real; no separate worker secret needed.

function unauthorized(detail: string) {
    return NextResponse.json({ status: 'error', detail }, { status: 401 })
}

async function isValidServiceRoleKey(candidateKey: string): Promise<boolean> {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
    if (!supabaseUrl || !candidateKey) return false
    try {
        const res = await fetch(`${supabaseUrl.replace(/\/$/, '')}/auth/v1/admin/users?page=1&per_page=1`, {
            headers: { apikey: candidateKey, Authorization: `Bearer ${candidateKey}` },
        })
        return res.ok
    } catch {
        return false
    }
}

async function isAuthorized(email: unknown, session_token: unknown, worker_key: unknown): Promise<boolean> {
    if (typeof worker_key === 'string' && worker_key.length > 0) {
        if (await isValidServiceRoleKey(worker_key)) return true
    }
    if (typeof email === 'string' && typeof session_token === 'string') {
        return verifyApprovedDesktopSession(email, session_token)
    }
    return false
}

export async function POST(req: Request) {
    let body: any
    try {
        body = await req.json()
    } catch {
        return NextResponse.json({ status: 'error', detail: 'invalid_json' }, { status: 400 })
    }

    const { email, session_token, worker_key } = body || {}
    if (!(await isAuthorized(email, session_token, worker_key))) {
        return unauthorized('invalid_or_expired_session')
    }

    const clientId = process.env.GOOGLE_DRIVE_CLIENT_ID
    const clientSecret = process.env.GOOGLE_DRIVE_CLIENT_SECRET
    const refreshToken = process.env.GOOGLE_DRIVE_REFRESH_TOKEN
    if (!clientId || !clientSecret || !refreshToken) {
        console.error('[DesktopDriveToken] Missing GOOGLE_DRIVE_* env configuration')
        return NextResponse.json({ status: 'error', detail: 'drive_credentials_not_configured' }, { status: 500 })
    }

    try {
        const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({
                client_id: clientId,
                client_secret: clientSecret,
                refresh_token: refreshToken,
                grant_type: 'refresh_token',
            }),
        })
        const tokenBody = await tokenRes.json()
        if (!tokenRes.ok || !tokenBody.access_token) {
            console.error('[DesktopDriveToken] Google token refresh failed:', tokenRes.status, tokenBody?.error)
            return NextResponse.json({ status: 'error', detail: 'drive_token_refresh_failed' }, { status: 502 })
        }

        return NextResponse.json({
            status: 'ok',
            access_token: tokenBody.access_token,
            expires_in: tokenBody.expires_in,
            root_folder_id: process.env.GOOGLE_DRIVE_ROOT_FOLDER_ID || null,
        })
    } catch (error: any) {
        console.error('[DesktopDriveToken] Error:', error?.message)
        return NextResponse.json({ status: 'error', detail: 'bridge_error' }, { status: 500 })
    }
}
