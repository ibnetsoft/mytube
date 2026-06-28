import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'

export const dynamic = 'force-dynamic'

const KEYS = [
    'gemini', 'youtube', 'claude', 'elevenlabs', 'topview', 'topview_uid',
    'suno', 'suno_base_url', 'music_provider',
    'music_gemini_model', 'music_gemini_base_url', 'music_gemini_project_id', 'music_gemini_location',
    'longform_min_duration_minutes', 'longform_base_payout', 'longform_extra_minute_payout',
    'longform_duration_lock_enabled',
    'script_generation_provider', 'script_generation_model',
    'image_prompt_provider', 'image_generation_model', 'video_generation_model'
]

const EXACT_KEYS = [
    'binance_api_key', 'binance_api_secret',
    'terms_ko', 'terms_en', 'terms_vi', 'terms_th',
    'privacy_ko', 'privacy_en', 'privacy_vi', 'privacy_th',
    'qa_enable_pipeline', 'qa_enable_technical_check', 'qa_enable_semantic_check',
    'qa_auto_normalize_lufs', 'qa_hold_on_technical_fail', 'qa_hold_on_semantic_fail',
    'qa_target_lufs', 'qa_lufs_tolerance', 'qa_blackdetect_min_duration',
    'qa_min_width', 'qa_min_height'
]

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const sb = getAdmin()
        const { data } = await sb.from('global_settings').select('key, value').in('key', [...KEYS.map(k => `sys_api_${k}`), ...EXACT_KEYS])
        const result: Record<string, string> = {}
        for (const row of (data || [])) {
            const k = row.key.startsWith('sys_api_') ? row.key.replace('sys_api_', '') : row.key
            result[k] = row.value || ''
        }
        return NextResponse.json(result)
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
            await sb.from('global_settings').upsert({ key: `sys_api_${k}`, value: body[k] }, { onConflict: 'key' })
        }
        for (const k of EXACT_KEYS) {
            if (body[k] === undefined) continue
            await sb.from('global_settings').upsert({ key: k, value: body[k] }, { onConflict: 'key' })
        }
        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
