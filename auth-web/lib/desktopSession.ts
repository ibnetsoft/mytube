import crypto from 'crypto'
import { supabaseAdmin } from './supabaseAdmin'

// [AIR-0225B Batch A] Desktop app session resume without re-sending a password.
//
// The desktop app's local FastAPI backend restores a login session purely from
// a long-lived browser cookie (services/auth_service.py's login_user(), called
// from main.py's cookie-based middleware, and app/routers/auth.py's
// /api/auth/sync). Before this file existed, that path re-fetched
// membership/token_balance/global API keys directly from Supabase using
// SUPABASE_SERVICE_ROLE_KEY - which is exactly the key we removed from the
// desktop package (see worknote/AIR-0225B-stage0-service-role-removal-investigation.md).
//
// Naively replacing that with "POST an email, get back membership/API keys"
// would be a straightforward account-enumeration / API-key-leak endpoint -
// anyone who knows (or guesses) an employee's email could pull their
// membership tier, token balance, and the shared Gemini/Claude/etc keys with
// no credential at all. So login (email+password, verified in
// /api/desktop-login) additionally mints an opaque, HMAC-signed session token
// that only this server can produce or verify. The desktop app stores it in a
// cookie next to the existing user_email cookie (HttpOnly - the desktop
// frontend JS never needs to read it, only the local Python backend forwards
// it) and presents BOTH email + token to /api/desktop-resync on every
// subsequent restart. Forging a token requires DESKTOP_SESSION_SECRET, which
// never leaves this server.

const TOKEN_VALIDITY_SECONDS = 30 * 24 * 60 * 60 // matches the desktop app's user_email cookie max_age
const CLOCK_SKEW_TOLERANCE_SECONDS = 60

function getSecret(): string {
    const secret = process.env.DESKTOP_SESSION_SECRET
    if (!secret) {
        throw new Error('DESKTOP_SESSION_SECRET is not configured')
    }
    return secret
}

export function signDesktopSessionToken(email: string): string {
    const issuedAt = Math.floor(Date.now() / 1000)
    const payload = `${email}.${issuedAt}`
    const sig = crypto.createHmac('sha256', getSecret()).update(payload).digest('hex')
    return Buffer.from(`${payload}.${sig}`, 'utf-8').toString('base64url')
}

export function verifyDesktopSessionToken(email: string, token: string): boolean {
    if (!email || !token) return false
    let secret: string
    try {
        secret = getSecret()
    } catch {
        return false
    }
    try {
        const decoded = Buffer.from(token, 'base64url').toString('utf-8')
        // NOTE: split on '.' and take the last two segments as issuedAt/sig,
        // then rejoin everything else as the email - a plain split('.') would
        // break on any email whose domain has a dot (i.e. virtually all of
        // them, e.g. "user@example.com" already has 2 dots on its own).
        const parts = decoded.split('.')
        if (parts.length < 3) return false
        const sigHex = parts.pop() as string
        const issuedAtStr = parts.pop() as string
        const tokenEmail = parts.join('.')
        if (tokenEmail !== email) return false

        const issuedAt = parseInt(issuedAtStr, 10)
        if (!Number.isFinite(issuedAt)) return false
        const now = Math.floor(Date.now() / 1000)
        if (now - issuedAt > TOKEN_VALIDITY_SECONDS) return false // expired
        if (issuedAt - now > CLOCK_SKEW_TOLERANCE_SECONDS) return false // issued in the future

        const expectedSig = crypto.createHmac('sha256', secret).update(`${tokenEmail}.${issuedAtStr}`).digest('hex')
        const sigBuf = Buffer.from(sigHex, 'hex')
        const expectedBuf = Buffer.from(expectedSig, 'hex')
        if (sigBuf.length !== expectedBuf.length) return false
        return crypto.timingSafeEqual(sigBuf, expectedBuf)
    } catch {
        return false
    }
}

// [AIR-0225B Batch A] global_settings 'sys_api_*' -> desktop app config key.
// Mirrors services/web_admin_client.py's WebAdminClient.KEY_MAP exactly - keep
// both in sync if either changes.
const SYS_KEY_MAP: Record<string, string> = {
    sys_api_gemini: 'GEMINI_API_KEY',
    sys_api_youtube: 'YOUTUBE_API_KEY',
    sys_api_claude: 'CLAUDE_API_KEY',
    sys_api_elevenlabs: 'ELEVENLABS_API_KEY',
    sys_api_suno: 'SUNO_API_KEY',
    sys_api_suno_base_url: 'SUNO_API_BASE_URL',
    sys_api_music_provider: 'MUSIC_PROVIDER',
    sys_api_music_gemini_model: 'MUSIC_GEMINI_MODEL',
    sys_api_music_gemini_base_url: 'MUSIC_GEMINI_BASE_URL',
    sys_api_music_gemini_project_id: 'MUSIC_GEMINI_PROJECT_ID',
    sys_api_music_gemini_location: 'MUSIC_GEMINI_LOCATION',
    sys_api_topview: 'TOPVIEW_API_KEY',
    sys_api_topview_uid: 'TOPVIEW_UID',
    sys_api_remote_render_drive_folder_id: 'REMOTE_RENDER_DRIVE_FOLDER_ID',
    sys_api_remote_render_google_token_path: 'REMOTE_RENDER_GOOGLE_TOKEN_PATH',
    sys_api_longform_min_duration_minutes: 'LONGFORM_MIN_DURATION_MINUTES',
    sys_api_longform_base_payout: 'LONGFORM_BASE_PAYOUT',
    sys_api_longform_extra_minute_payout: 'LONGFORM_EXTRA_MINUTE_PAYOUT',
    sys_api_longform_duration_lock_enabled: 'LONGFORM_DURATION_LOCK_ENABLED',
    sys_api_topic_generation_model: 'TOPIC_GENERATION_MODEL',
    sys_api_title_generation_model: 'TITLE_GENERATION_MODEL',
    sys_api_script_planning_model: 'SCRIPT_PLANNING_MODEL',
    sys_api_script_generation_model: 'SCRIPT_GENERATION_MODEL',
    sys_api_image_prompt_model: 'IMAGE_PROMPT_MODEL',
    sys_api_translation_model: 'TRANSLATION_MODEL',
    sys_api_image_generation_model: 'IMAGE_GENERATION_MODEL',
    sys_api_video_generation_model: 'VIDEO_GENERATION_MODEL',
    latest_app_version: 'LATEST_APP_VERSION',
    latest_app_url: 'LATEST_APP_URL',
}

export const DESKTOP_ALLOWED_LANGS = new Set(['ko', 'en', 'vi', 'th'])

export interface DesktopProfileSnapshot {
    membership: string
    token_balance: number
    preferred_language: string
    global_settings: { key: string; value: string }[]
    full_name: string
    nationality: string
    contact: string
    referral_code: string
    preferred_category_ids: (string | number)[]
    preferred_video_length: string
    categories: { id: string | number; name: string; video_type: string }[]
}

/**
 * Fetches everything the desktop app needs right after a session is
 * established (fresh password login, or a verified resync) in one place, so
 * /api/desktop-login and /api/desktop-resync return an identical shape.
 * Returns null if no profile row exists for the email.
 *
 * [AIR-0225B Phase 1] Also carries the settings-page profile fields
 * (full_name/nationality/contact/referral_code/preferred_category_ids/
 * preferred_video_length) and the categories list - these used to be fetched
 * by the desktop app directly from Supabase with SUPABASE_SERVICE_ROLE_KEY
 * (services/web_admin_client.py's fetch_profile_by_email/fetch_categories),
 * which stopped working once that key was removed from the packaged app
 * (worknote/AIR-0225B-stage0-service-role-removal-investigation.md Phase 2).
 */
export async function fetchDesktopProfileSnapshot(
    email: string,
    lang?: string
): Promise<{ profile: DesktopProfileSnapshot; isApproved: boolean } | null> {
    const { data: profile, error } = await supabaseAdmin
        .from('profiles')
        .select('is_approved, preferred_language, membership, token_balance, full_name, nationality, contact, referral_code, preferred_category_ids, preferred_video_length')
        .eq('email', email)
        .maybeSingle()

    if (error) {
        throw new Error(`Profile fetch error: ${error.message}`)
    }
    if (!profile) {
        return null
    }

    const isApproved = !(
        profile.is_approved === false ||
        profile.is_approved === null ||
        profile.is_approved === undefined ||
        ['false', '0', 'none'].includes(String(profile.is_approved).toLowerCase())
    )

    let effectiveLang = profile.preferred_language || ''
    if (lang && DESKTOP_ALLOWED_LANGS.has(lang) && lang !== profile.preferred_language) {
        effectiveLang = lang
        const { error: langError } = await supabaseAdmin
            .from('profiles')
            .update({ preferred_language: effectiveLang })
            .eq('email', email)
        if (langError) {
            console.warn('[DesktopSession] preferred_language update warning:', langError.message)
        }
    }

    let globalSettings: { key: string; value: string }[] = []
    try {
        const { data: sysSettings, error: sysError } = await supabaseAdmin
            .from('global_settings')
            .select('key, value')
            .in('key', Object.keys(SYS_KEY_MAP))
        if (sysError) {
            console.warn('[DesktopSession] global_settings fetch warning:', sysError.message)
        } else if (sysSettings) {
            globalSettings = sysSettings
        }
    } catch (sysErr: any) {
        console.warn('[DesktopSession] global_settings fetch error:', sysErr?.message)
    }

    let categories: { id: string | number; name: string; video_type: string }[] = []
    try {
        const { data: catRows, error: catError } = await supabaseAdmin
            .from('categories')
            .select('id, name, video_type')
            .order('created_at', { ascending: false })
        if (catError) {
            console.warn('[DesktopSession] categories fetch warning:', catError.message)
        } else if (catRows) {
            categories = catRows
        }
    } catch (catErr: any) {
        console.warn('[DesktopSession] categories fetch error:', catErr?.message)
    }

    return {
        isApproved,
        profile: {
            membership: profile.membership || 'std',
            token_balance: profile.token_balance ?? 0,
            preferred_language: effectiveLang,
            global_settings: globalSettings,
            full_name: profile.full_name || '',
            nationality: profile.nationality || '',
            contact: profile.contact || '',
            referral_code: profile.referral_code || '',
            preferred_category_ids: profile.preferred_category_ids || [],
            preferred_video_length: profile.preferred_video_length || '',
            categories,
        },
    }
}
