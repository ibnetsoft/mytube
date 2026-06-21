
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

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
        const { userId, hwid } = await req.json()

        if (!userId) {
            return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
        }

        // Get user app_metadata
        const { data: { user }, error } = await supabaseAdmin.auth.admin.getUserById(userId)

        if (error || !user) {
            return NextResponse.json({ error: 'Invalid license key' }, { status: 401 })
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
        const isPro = String(membership).toLowerCase() === 'pro';

        // 1. 시스템 전역 키 조회 (공용 fallback) - PRO 모드가 아닐 때만
        const sys_keys: Record<string, string> = {}
        if (!isPro) {
            try {
                const KEYS = ['gemini', 'youtube', 'elevenlabs', 'topview', 'topview_uid']
                const { data: sysSettings } = await supabaseAdmin
                    .from('global_settings')
                    .select('key, value')
                    .in('key', KEYS.map(k => `sys_api_${k}`))
                
                if (sysSettings) {
                    const sysMap: Record<string, string> = {
                        sys_api_gemini:     'GEMINI_API_KEY',
                        sys_api_youtube:    'YOUTUBE_API_KEY',
                        sys_api_elevenlabs: 'ELEVENLABS_API_KEY',
                        sys_api_topview:    'TOPVIEW_API_KEY',
                        sys_api_topview_uid: 'TOPVIEW_UID',
                    }
                    for (const row of sysSettings) {
                        const configKey = sysMap[row.key]
                        if (configKey && row.value) {
                            sys_keys[configKey] = row.value
                        }
                    }
                }
            } catch (sysErr) {
                console.warn('[Verify] Failed to load global_settings fallback:', sysErr)
            }
        }

        // 2. 유저 개별 키 조회 및 병합 (PRO 모드면 sys_keys가 비어있음 -> 공통 API 무시)
        const api_keys: Record<string, string> = { ...sys_keys }
        
        // 과거 meta 필드 지원
        const keyMap: Record<string, string> = {
            gemini_api_key:     'GEMINI_API_KEY',
            youtube_api_key:    'YOUTUBE_API_KEY',
            elevenlabs_api_key: 'ELEVENLABS_API_KEY',
            topview_api_key:    'TOPVIEW_API_KEY',
            topview_uid:        'TOPVIEW_UID',
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
            membership: profile?.membership || user.app_metadata?.membership || 'std',
            email: user.email,
            pin_code: profile?.pin_code || '1234',
            full_name: meta.full_name || '',
            nationality: meta.nationality || '',
            contact: meta.contact || '',
            youtube_channel: meta.youtube_channel || '',
            youtube_handle: meta.youtube_handle || '',
            token_balance: tokenBalance,
            api_keys,              // 메모리 전용 로드 — 로컬 저장 안 함
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
