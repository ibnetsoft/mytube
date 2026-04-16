
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    
    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: { autoRefreshToken: false, persistSession: false }
    })

    try {
        const { userId, amount, description } = await req.json()
        
        if (!userId || !amount) {
            return NextResponse.json({ success: false, error: 'Missing parameters' }, { status: 400 })
        }

        // rpc 호출 (migration_token_system.sql에서 생성한 recharge_tokens 함수)
        const { data, error } = await supabaseAdmin.rpc('recharge_tokens', {
            p_user_id: userId,
            p_amount: amount,
            p_description: description || '관리자 충전'
        })

        if (error) throw error

        return NextResponse.json({ success: true, data })
    } catch (error: any) {
        console.error('Recharge Error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
