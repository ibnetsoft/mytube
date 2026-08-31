import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'
import { deleteServerCache, getServerCache, setServerCache } from '@/lib/server-cache'

export const dynamic = 'force-dynamic'
const GLOBAL_SETTINGS_CACHE_KEY = 'admin:settings:global'
const GLOBAL_SETTINGS_CACHE_TTL_SECONDS = 300

const KEYS = [
    'gemini', 'youtube', 'youtube_keys', 'claude', 'elevenlabs', 'elevenlabs_keys', 'topview', 'topview_uid',
    'suno', 'suno_base_url', 'music_provider',
    'google_drive_client_id', 'google_drive_client_secret', 'google_drive_refresh_token', 'google_drive_root_folder_id',
    'music_gemini_model', 'music_gemini_base_url', 'music_gemini_project_id', 'music_gemini_location',
    'longform_min_duration_minutes', 'longform_base_payout', 'longform_extra_minute_payout',
    'longform_payout_tiers',
    'longform_duration_lock_enabled',
    'topic_generation_model', 'title_generation_model', 'script_planning_model',
    'script_generation_model', 'image_prompt_model', 'translation_model',
    'image_generation_model', 'video_generation_model',
    'drive_render_queue_path', 'use_external_render'
]

const EXACT_KEYS = [
    'binance_api_key', 'binance_api_secret',
    'terms_ko', 'terms_en', 'terms_vi', 'terms_th',
    'privacy_ko', 'privacy_en', 'privacy_vi', 'privacy_th',
    'qa_enable_pipeline', 'qa_enable_technical_check', 'qa_enable_semantic_check',
    'qa_auto_normalize_lufs', 'qa_hold_on_technical_fail', 'qa_hold_on_semantic_fail',
    'qa_target_lufs', 'qa_lufs_tolerance', 'qa_blackdetect_min_duration',
    'qa_min_width', 'qa_min_height',
    // [AIR-0230] 모델별 단가표 - JSON 문자열로 저장 { [model_id]: { input_per_1k, output_per_1k, thinking_per_1k, currency } }
    'model_pricing',
    // 씬 전환 효과 - 유저 설정에서 어드민 전용 제어로 이전
    'scene_transition_mode'
]

const SECRET_KEYS = new Set([
    'gemini',
    'youtube',
    'youtube_keys',
    'claude',
    'elevenlabs',
    'elevenlabs_keys',
    'topview',
    'suno',
])

function isMaskedOrEmptySecretValue(value: unknown): boolean {
    const normalized = String(value ?? '').trim()
    if (!normalized) return true
    if (/^[•*]+$/.test(normalized)) return true
    if (['(미설정)', '(unset)', 'undefined', 'null'].includes(normalized.toLowerCase())) return true
    return false
}

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const cached = await getServerCache<Record<string, string>>(GLOBAL_SETTINGS_CACHE_KEY)
        if (cached) {
            return NextResponse.json(cached, {
                headers: {
                    'Cache-Control': `private, max-age=${GLOBAL_SETTINGS_CACHE_TTL_SECONDS}`,
                    'X-Admin-Cache': 'HIT',
                },
            })
        }

        const sb = getAdmin()
        const { data } = await sb.from('global_settings').select('key, value').in('key', [...KEYS.map(k => `sys_api_${k}`), ...EXACT_KEYS])
        const result: Record<string, string> = {}
        for (const row of (data || [])) {
            const k = row.key.startsWith('sys_api_') ? row.key.replace('sys_api_', '') : row.key
            result[k] = row.value || ''
        }
        await setServerCache(GLOBAL_SETTINGS_CACHE_KEY, result, GLOBAL_SETTINGS_CACHE_TTL_SECONDS)
        return NextResponse.json(result, {
            headers: {
                'Cache-Control': `private, max-age=${GLOBAL_SETTINGS_CACHE_TTL_SECONDS}`,
                'X-Admin-Cache': 'MISS',
            },
        })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const sb = getAdmin()
        for (const k of KEYS) {
            if (body[k] === undefined) continue
            if (SECRET_KEYS.has(k) && isMaskedOrEmptySecretValue(body[k])) continue
            const { error } = await sb.from('global_settings').upsert({ key: `sys_api_${k}`, value: body[k] }, { onConflict: 'key' })
            if (error) throw new Error(`global_settings save failed for sys_api_${k}: ${error.message}`)
        }
        for (const k of EXACT_KEYS) {
            if (body[k] === undefined) continue
            const { error } = await sb.from('global_settings').upsert({ key: k, value: body[k] }, { onConflict: 'key' })
            if (error) throw new Error(`global_settings save failed for ${k}: ${error.message}`)
        }
        await deleteServerCache(GLOBAL_SETTINGS_CACHE_KEY)
        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
