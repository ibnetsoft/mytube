
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
        const { userId } = await req.json()

        if (!userId) {
            return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
        }

        // Get user app_metadata
        const { data: { user }, error } = await supabaseAdmin.auth.admin.getUserById(userId)

        if (error || !user) {
            return NextResponse.json({ error: 'Invalid license key' }, { status: 401 })
        }

        const meta = user.user_metadata || {}

        // API 키를 Config 키 이름으로 매핑하여 반환
        const api_keys: Record<string, string> = {}
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

        // Get user profile (token balance)
        const { data: profile, error: profileError } = await supabaseAdmin
            .from('profiles')
            .select('token_balance')
            .eq('id', userId)
            .maybeSingle()

        if (profileError) {
            console.warn(`[Verify] Profile fetch error for ${userId}:`, profileError.message)
        }

        const tokenBalance = profile?.token_balance ?? 0
        console.log(`Verify SUCCESS for user ${userId}: channel=${meta.youtube_channel}, token_balance=${tokenBalance}`);
        return NextResponse.json({
            success: true,
            membership: user.app_metadata?.membership || 'std',
            email: user.email,
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
