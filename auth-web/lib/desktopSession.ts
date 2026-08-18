import crypto from 'crypto'
import { supabaseAdmin } from './supabaseAdmin'

const TOKEN_VALIDITY_SECONDS = 30 * 24 * 60 * 60 // 30 days
const CLOCK_SKEW_TOLERANCE_SECONDS = 60

function getSecret(): string {
    const secret = process.env.DESKTOP_SESSION_SECRET || process.env.SUPABASE_SERVICE_ROLE_KEY || 'air-studio-desktop-session-secret'
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
        const parts = decoded.split('.')
        if (parts.length < 3) return false
        const sigHex = parts.pop() as string
        const issuedAtStr = parts.pop() as string
        const tokenEmail = parts.join('.')
        if (tokenEmail.toLowerCase() !== email.toLowerCase()) return false

        const issuedAt = parseInt(issuedAtStr, 10)
        if (!Number.isFinite(issuedAt)) return false
        const now = Math.floor(Date.now() / 1000)
        if (now - issuedAt > TOKEN_VALIDITY_SECONDS) return false
        if (issuedAt - now > CLOCK_SKEW_TOLERANCE_SECONDS) return false

        const expectedSig = crypto.createHmac('sha256', secret).update(`${tokenEmail}.${issuedAtStr}`).digest('hex')
        const sigBuf = Buffer.from(sigHex, 'hex')
        const expectedBuf = Buffer.from(expectedSig, 'hex')
        if (sigBuf.length !== expectedBuf.length) return false
        return crypto.timingSafeEqual(sigBuf, expectedBuf)
    } catch {
        return false
    }
}

export function getEmailFromDesktopToken(token: string): string | null {
    if (!token) return null
    let secret: string
    try {
        secret = getSecret()
    } catch {
        return null
    }
    try {
        const decoded = Buffer.from(token, 'base64url').toString('utf-8')
        const parts = decoded.split('.')
        if (parts.length < 3) return null
        const sigHex = parts.pop() as string
        const issuedAtStr = parts.pop() as string
        const tokenEmail = parts.join('.')

        const issuedAt = parseInt(issuedAtStr, 10)
        if (!Number.isFinite(issuedAt)) return null
        const now = Math.floor(Date.now() / 1000)
        if (now - issuedAt > TOKEN_VALIDITY_SECONDS) return null
        if (issuedAt - now > CLOCK_SKEW_TOLERANCE_SECONDS) return null

        const expectedSig = crypto.createHmac('sha256', secret).update(`${tokenEmail}.${issuedAtStr}`).digest('hex')
        const sigBuf = Buffer.from(sigHex, 'hex')
        const expectedBuf = Buffer.from(expectedSig, 'hex')
        if (sigBuf.length !== expectedBuf.length) return null
        if (!crypto.timingSafeEqual(sigBuf, expectedBuf)) return null

        return tokenEmail
    } catch {
        return null
    }
}

export async function verifyApprovedDesktopSession(email: string, token: string): Promise<boolean> {
    if (!verifyDesktopSessionToken(email, token)) return false

    const { data: profile, error } = await supabaseAdmin
        .from('profiles')
        .select('is_approved')
        .eq('email', email)
        .maybeSingle()
    if (error || !profile) return false

    return !(
        profile.is_approved === false ||
        profile.is_approved === null ||
        profile.is_approved === undefined ||
        ['false', '0', 'none'].includes(String(profile.is_approved).toLowerCase())
    )
}

const SYS_KEY_MAP: Record<string, string> = {
    sys_api_gemini: 'GEMINI_API_KEY',
    sys_api_youtube: 'YOUTUBE_API_KEY',
    sys_api_youtube_keys: 'YOUTUBE_API_KEYS',
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
    sys_api_topic_queue_batch_size: 'TOPIC_QUEUE_BATCH_SIZE',
    sys_api_topic_similarity_threshold: 'TOPIC_SIMILARITY_THRESHOLD',
}

export type DesktopProfileSnapshot = {
    email: string
    isApproved: boolean
    profile: {
        preferred_language: string
        membership: string
        token_balance: number
        global_settings: Record<string, string>
        full_name: string
        nationality: string
        contact: string
        referral_code: string
        preferred_category_ids: any[]
        preferred_video_length: string
        categories: any[]
    }
}

export async function fetchDesktopProfileSnapshot(
    email: string,
    preferredLanguageToSave?: string
): Promise<DesktopProfileSnapshot | null> {
    const { data: profile, error } = await supabaseAdmin
        .from('profiles')
        .select('is_approved,membership,token_balance,preferred_languages,full_name,nationality,contact,referral_code,preferred_category_ids,preferred_video_length')
        .eq('email', email)
        .maybeSingle()

    if (error || !profile) {
        return null
    }

    let preferredLang = 'en'
    if (Array.isArray(profile.preferred_languages) && profile.preferred_languages.length > 0) {
        preferredLang = String(profile.preferred_languages[0] || 'en')
    }

    if (preferredLanguageToSave && preferredLanguageToSave !== preferredLang) {
        preferredLang = preferredLanguageToSave
        await supabaseAdmin
            .from('profiles')
            .update({ preferred_languages: [preferredLanguageToSave] })
            .eq('email', email)
    }

    const { data: settingsRows } = await supabaseAdmin
        .from('global_settings')
        .select('key,value')
        .in('key', Object.keys(SYS_KEY_MAP))

    const { data: categoriesRows } = await supabaseAdmin
        .from('categories')
        .select('id,name')
        .order('name', { ascending: true })

    const globalSettings: Record<string, string> = {}
    for (const row of settingsRows || []) {
        const destKey = SYS_KEY_MAP[row.key]
        if (destKey && row.value) {
            globalSettings[destKey] = row.value
        }
    }

    const isApproved = !(
        profile.is_approved === false ||
        profile.is_approved === null ||
        profile.is_approved === undefined ||
        ['false', '0', 'none'].includes(String(profile.is_approved).toLowerCase())
    )

    return {
        email,
        isApproved,
        profile: {
            preferred_language: preferredLang,
            membership: profile.membership || 'std',
            token_balance: profile.token_balance || 0,
            global_settings: globalSettings,
            full_name: profile.full_name || '',
            nationality: profile.nationality || '',
            contact: profile.contact || '',
            referral_code: profile.referral_code || '',
            preferred_category_ids: Array.isArray(profile.preferred_category_ids) ? profile.preferred_category_ids : [],
            preferred_video_length: profile.preferred_video_length || '',
            categories: (categoriesRows || []).map((row: any) => ({
                ...row,
                video_type: row.video_type || 'longform',
            })),
        },
    }
}
