import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY
    
    if (!supabaseServiceKey) {
        return NextResponse.json({ success: false, error: 'SERVICE_ROLE_KEY is missing' }, { status: 500 })
    }

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: { autoRefreshToken: false, persistSession: false }
    })

    try {
        const { userId, amount, description } = await req.json()
        
        if (!userId || !amount) {
            return NextResponse.json({ success: false, error: 'Missing parameters' }, { status: 400 })
        }

        console.log(`[Recharge] Starting recharge for ${userId}, amount: ${amount}`);

        // 1. 프로필 존재 여부 확인 및 자동 생성 (UPSERT 전략)
        const { data: profile, error: checkError } = await supabaseAdmin
            .from('profiles')
            .select('id')
            .eq('id', userId)
            .single()

        if (checkError || !profile) {
            console.log(`[Recharge] Profile not found for ${userId}, creating initial profile...`);
            const { error: insertError } = await supabaseAdmin
                .from('profiles')
                .insert({ id: userId, token_balance: 0, membership_tier: 'standard' })
            
            if (insertError) {
                console.error("[Recharge] Profile creation failed:", insertError);
                // Continue anyway, RPC might handle it or fail safely
            }
        }

        // 2. rpc 호출 (token_balance 업데이트 및 트랜잭션 기록)
        const { data, error } = await supabaseAdmin.rpc('recharge_tokens', {
            p_user_id: userId,
            p_amount: amount,
            p_description: description || '관리자 충전'
        })

        if (error) {
            console.error('[Recharge] RPC Error:', error);
            throw error
        }

        console.log(`[Recharge] Successfully recharged user ${userId}`);
        return NextResponse.json({ success: true, data })
    } catch (error: any) {
        console.error('[Recharge] Final Error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
