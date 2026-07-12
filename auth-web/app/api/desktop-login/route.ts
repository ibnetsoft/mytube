import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

// 데스크톱 앱(AIR Studio)의 로그인 검증을 서버에서 대신 수행한다.
// SUPABASE_SERVICE_ROLE_KEY는 이 서버 프로세스 밖으로 절대 나가지 않으며,
// 데스크톱 앱은 email/password만 보내고 검증 결과만 돌려받는다.
// [AIR-0225B Batch A] global_settings 'sys_api_*' -> desktop app config key.
// Mirrors services/web_admin_client.py's WebAdminClient.KEY_MAP exactly - keep
// both in sync if either changes. Only used to relay raw key/value rows; no
// key material lives in this file beyond what's already in global_settings.
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

const ALLOWED_LANGS = new Set(['ko', 'en', 'vi', 'th'])

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: {
            autoRefreshToken: false,
            persistSession: false
        }
    })

    try {
        const { email, password, lang } = await req.json()

        if (!email || !password) {
            return NextResponse.json({ success: false, error: 'Missing email or password' }, { status: 400 })
        }

        // NOTE: profiles has no 'password' column, only 'pin_code' (confirmed
        // against the live schema) - matches the desktop app's original
        // fallback logic which always ended up on pin_code in practice.
        // [AIR-0225B Batch A] Also select membership/token_balance so the
        // desktop app no longer needs its own service_role-backed
        // fetch_profile_by_email() call right after login.
        const { data: profile, error } = await supabaseAdmin
            .from('profiles')
            .select('is_approved, pin_code, preferred_language, membership, token_balance')
            .eq('email', String(email))
            .maybeSingle()

        if (error) {
            console.error('[DesktopLogin] Profile fetch error:', error.message)
            return NextResponse.json({ success: false, error: '로그인 서버 오류' }, { status: 500 })
        }

        if (!profile) {
            return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
        }

        const isApproved = profile.is_approved
        if (isApproved === false || isApproved === null || isApproved === undefined || ['false', '0', 'none'].includes(String(isApproved).toLowerCase())) {
            return NextResponse.json({ success: false, error: '어드민 승인 대기 중이거나 비활성화된 계정입니다.' }, { status: 403 })
        }

        const dbPassword = String(profile.pin_code || '1234').trim()
        const inputPassword = String(password).trim()

        if (dbPassword !== inputPassword) {
            return NextResponse.json({ success: false, error: '비밀번호가 일치하지 않습니다.' }, { status: 401 })
        }

        // [AIR-0225B Batch A] Save the client-resolved display language in the
        // same round trip as login, replacing the desktop app's separate
        // service_role-backed update_preferred_language() call. Best-effort:
        // a failure here must not fail the login itself.
        let effectiveLang = profile.preferred_language || ''
        if (lang && ALLOWED_LANGS.has(String(lang))) {
            effectiveLang = String(lang)
            if (effectiveLang !== profile.preferred_language) {
                const { error: langError } = await supabaseAdmin
                    .from('profiles')
                    .update({ preferred_language: effectiveLang })
                    .eq('email', String(email))
                if (langError) {
                    console.warn('[DesktopLogin] preferred_language update warning:', langError.message)
                }
            }
        }

        // [AIR-0225B Batch A] Global (non-PRO-only) shared API keys, replacing
        // the desktop app's separate service_role-backed fetch_global_api_keys().
        // Raw key/value rows are relayed as-is; the desktop app applies the
        // same SYS_KEY_MAP translation locally (services/web_admin_client.py
        // KEY_MAP) so the mapping only needs to be reasoned about in one place
        // at a time, mirrored here for the response shape only.
        let globalSettings: { key: string; value: string }[] = []
        try {
            const { data: sysSettings, error: sysError } = await supabaseAdmin
                .from('global_settings')
                .select('key, value')
                .in('key', Object.keys(SYS_KEY_MAP))
            if (sysError) {
                console.warn('[DesktopLogin] global_settings fetch warning:', sysError.message)
            } else if (sysSettings) {
                globalSettings = sysSettings
            }
        } catch (sysErr: any) {
            console.warn('[DesktopLogin] global_settings fetch error:', sysErr?.message)
        }

        return NextResponse.json({
            success: true,
            preferred_language: effectiveLang,
            membership: profile.membership || 'std',
            token_balance: profile.token_balance ?? 0,
            global_settings: globalSettings,
        })
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
