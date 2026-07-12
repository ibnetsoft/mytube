
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0227F-0 P0 hotfix]
//
// This endpoint used to authenticate the caller by trusting a bare `userId`
// in the request body, with an HWID check that (per a follow-up audit -
// docs/AIR_0227F_DESKTOP_AUTH_REDESIGN.md §5-1) never actually gated
// anything: approved_hwid/device_hwid are never written anywhere in this
// codebase, so the comparison was always against an empty value. Anyone who
// obtained a valid, approved userId could call this endpoint and receive
// that user's profile plus a merged api_keys object - including shared,
// platform-owned provider keys (Gemini/YouTube/ElevenLabs/TopView/Claude)
// for non-PRO accounts.
//
// Two changes, deliberately staged differently by risk:
//
// 1. Platform system keys (sys_api_*) are removed from this response
//    UNCONDITIONALLY, regardless of auth state. This is the actual
//    credential-leak containment and ships immediately. It does not break
//    currently-running desktop clients: login_user() in
//    services/auth_service.py already loads these same keys via
//    /api/desktop-login and /api/desktop-resync's `global_settings` field
//    (see desktopSession.ts::fetchDesktopProfileSnapshot) - a properly
//    authenticated channel this hotfix does not touch. Removing them here
//    only means a running app's system keys stop refreshing on this
//    endpoint's ~30s poll cycle (services/auth_service.py::start_monitoring)
//    until the next login/resync, not an immediate loss of already-loaded
//    keys.
//
// 2. A session token (Authorization: Bearer <token>, the same HMAC-signed
//    token desktop-login already issues via signDesktopSessionToken) is now
//    ACCEPTED and, when present, VERIFIED against the resolved user's
//    email - a bad/mismatched token is rejected. But a MISSING token is
//    still allowed through for now: no client build that sends this token
//    has shipped yet (this session has no way to package/distribute one),
//    and hard-requiring it immediately would make this endpoint's ~30s
//    poll cycle fail for every currently-running install within seconds,
//    which is a materially worse outcome than the vulnerability itself.
//    This is a deliberate, temporary lenient period - see
//    docs/AIR_0227F_DESKTOP_AUTH_REDESIGN.md for the plan to make the token
//    mandatory once a client build that sends it has actually reached
//    users.
export async function POST(req: Request) {
    try {
        const { userId, hwid } = await req.json()

        if (!userId) {
            return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
        }

        // Get user app_metadata
        const { data: { user }, error } = await supabaseAdmin.auth.admin.getUserById(userId)

        if (error || !user) {
            return NextResponse.json({ error: 'Invalid license key' }, { status: 401 })
        }

        // Session token: verified when present, not yet required. A token
        // that fails verification is rejected outright (not silently
        // downgraded to "no token") - only an absent Authorization header is
        // treated leniently.
        //
        // [AIR-0227F-0B Stage 2] hasValidToken gates whether this response
        // includes raw personal API key values (below) - a request with no
        // token, or a garbage token, gets zero raw key material. A request
        // with a genuinely valid token still gets raw values FOR NOW - this
        // is the one remaining "temporary compatibility exception" the
        // task spec explicitly allows, because personal keys have no
        // alternate authenticated delivery channel the way platform system
        // keys do (those are also delivered via /api/desktop-login and
        // /api/desktop-resync's global_settings; personal
        // user_metadata/app_metadata keys are ONLY ever delivered here).
        // Deprecation plan: once BYOK/server-proxy work (AIR-0227F-0B
        // Stage 9) lands, this endpoint stops returning raw key material
        // at all, token or not - see docs/AIR_0227F_DESKTOP_AUTH_REDESIGN.md.
        const authHeader = req.headers.get('authorization') || ''
        const bearerMatch = /^Bearer\s+(\S+)$/.exec(authHeader)
        let hasValidToken = false
        if (bearerMatch && user.email) {
            const tokenValid = verifyDesktopSessionToken(user.email, bearerMatch[1])
            if (!tokenValid) {
                return NextResponse.json({ error: 'Invalid or expired session token' }, { status: 401 })
            }
            hasValidToken = true
        }

        const meta = user.user_metadata || {}
        const appMeta = user.app_metadata || {}
        if (appMeta.banned || appMeta.restricted || meta.banned || meta.restricted) {
            return NextResponse.json({ error: 'Account is restricted', status: 'restricted' }, { status: 403 })
        }

        // Get user profile first to determine membership
        let profile: {
            token_balance?: any
            membership?: any
            pin_code?: any
            is_approved?: any
            approved_hwid?: any
            device_hwid?: any
        } | null = null
        let profileError: any = null

        const profileResult = await supabaseAdmin
            .from('profiles')
            .select('token_balance, membership, pin_code, is_approved, approved_hwid, device_hwid')
            .eq('id', userId)
            .maybeSingle()
        profile = profileResult.data
        profileError = profileResult.error

        if (profileError) {
            console.warn(`[Verify] Profile fetch error for ${userId}:`, profileError.message)
            const fallback = await supabaseAdmin
                .from('profiles')
                .select('token_balance, membership, pin_code, is_approved')
                .eq('id', userId)
                .maybeSingle()
            profile = fallback.data
            profileError = fallback.error
        }

        if (profileError) {
            console.warn(`[Verify] Profile fallback fetch error for ${userId}:`, profileError.message)
        }

        const membership = profile?.membership || user.app_metadata?.membership || 'std';

        // [AIR-0227F-0 P0 hotfix] platform system keys removed entirely -
        // see file header. Personal (user-owned) keys below.
        //
        // [AIR-0227F-0B Stage 2] raw personal key values are now ONLY
        // populated when hasValidToken is true. A token-less request gets
        // api_keys: {} - safe by construction, not just by convention:
        // services/auth_service.py::Config.load_remote_keys() iterates
        // key/value pairs and no-ops on an empty dict, so old clients
        // degrade to "no personal keys loaded" rather than crashing. This
        // is a real functional loss for accounts using personal/custom
        // keys (not the free-tier system-shared keys, which remain
        // available via the already-authenticated desktop-login/resync
        // channel) until they run a build that sends the session token.
        // Deprecation plan for the valid-token exception itself: Stage 9
        // (BYOK/server-proxy).
        const api_keys: Record<string, string> = {}

        if (hasValidToken) {
            // 과거 meta 필드 지원
            const keyMap: Record<string, string> = {
                gemini_api_key:     'GEMINI_API_KEY',
                youtube_api_key:    'YOUTUBE_API_KEY',
                elevenlabs_api_key: 'ELEVENLABS_API_KEY',
                topview_api_key:    'TOPVIEW_API_KEY',
                topview_uid:        'TOPVIEW_UID',
                claude_api_key:     'CLAUDE_API_KEY',
            }
            for (const [metaKey, configKey] of Object.entries(keyMap)) {
                if (meta[metaKey]) api_keys[configKey] = meta[metaKey]
            }

            // app_metadata의 custom_api_keys 우선 적용
            const customKeys = appMeta.custom_api_keys || {}
            if (customKeys.openai) api_keys['OPENAI_API_KEY'] = customKeys.openai
            if (customKeys.gemini) api_keys['GEMINI_API_KEY'] = customKeys.gemini
            if (customKeys.pexels) api_keys['PEXELS_API_KEY'] = customKeys.pexels
            if (customKeys.replicate) api_keys['REPLICATE_API_KEY'] = customKeys.replicate
            if (customKeys.elevenlabs) api_keys['ELEVENLABS_API_KEY'] = customKeys.elevenlabs
            if (customKeys.youtube) api_keys['YOUTUBE_API_KEY'] = customKeys.youtube
            if (customKeys.claude) api_keys['CLAUDE_API_KEY'] = customKeys.claude
        }

        const isApproved = profile?.is_approved
        if (isApproved === false || isApproved === null || isApproved === undefined || ['false', '0', 'none'].includes(String(isApproved).toLowerCase())) {
            return NextResponse.json({ error: 'Account is waiting for admin approval', status: 'restricted' }, { status: 403 })
        }

        const registeredHwid = String(profile?.approved_hwid || profile?.device_hwid || '').trim()
        const incomingHwid = String(hwid || '').trim()
        if (registeredHwid && incomingHwid && registeredHwid !== incomingHwid) {
            return NextResponse.json({ error: 'Device is not approved for this account', status: 'restricted' }, { status: 403 })
        }

        const tokenBalance = profile?.token_balance ?? 0
        console.log(`Verify SUCCESS for user ${userId}: channel=${meta.youtube_channel}, token_balance=${tokenBalance}`);
        return NextResponse.json({
            success: true,
            membership,
            email: user.email,
            full_name: meta.full_name || '',
            nationality: meta.nationality || '',
            contact: meta.contact || '',
            youtube_channel: meta.youtube_channel || '',
            youtube_handle: meta.youtube_handle || '',
            token_balance: tokenBalance,
            api_keys,              // 메모리 전용 로드 — 로컬 저장 안 함 (개인 키만, 플랫폼 시스템 키 없음)
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
