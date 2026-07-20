import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
    const requester = await requireAdmin(req)
    if (isAuthResponse(requester)) return requester

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

    if (!supabaseServiceKey) {
        return NextResponse.json({ error: 'Server configuration error' }, { status: 500 })
    }

    try {
        const { userId, approved } = await req.json()
        if (!userId || approved === undefined) {
            return NextResponse.json({ error: 'Missing userId or approved status' }, { status: 400 })
        }

        const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
            auth: { persistSession: false }
        })

        const isApproved = Boolean(approved)

        // [AIR-0225B] 승인 시 토큰 자동 지급 폐지. 과금 모델이 잔액 차감에서
        // 사용량 누적(metering)으로 바뀌면서, 가입/승인 시점에 토큰을 지급하지
        // 않는다 (예전엔 최초 승인 시 100만 토큰을 충전했다). 승인은 이제
        // is_approved/signup_status 상태만 바꾼다. 필요 시 관리자가
        // recharge_tokens 로 개별 지급할 수 있다.
        const updates: Record<string, unknown> = {
            is_approved: isApproved,
            signup_status: isApproved ? 'approved' : 'pending'
        }

        const { error: profileError } = await supabaseAdmin
            .from('profiles')
            .update(updates)
            .eq('id', userId)

        if (profileError) throw profileError

        return NextResponse.json({ success: true })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
