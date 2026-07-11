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

        // 최초 승인 시 STD 회원에게 100만 토큰 자동 충전.
        // 재승인(이미 승인된 적 있는 계정을 다시 승인)이거나 PRO 회원, 또는 이미
        // 잔액이 있는 계정(과거에 지급/충전됨)은 중복 지급 방지를 위해 제외.
        // [AIR-FIX] profiles.token_balance의 DB 컬럼 기본값이 50000이라, 신규
        // 가입 계정은 승인 시점에 이미 50000을 갖고 있어 "=== 0" 조건이 실질적으로
        // 절대 참이 되지 않아 이 로직이 한 번도 실행된 적이 없었다. 실제 스타터
        // 잔액(50000) 이하인 경우까지 "아직 지급 안 됨"으로 간주하도록 수정.
        const { data: existingProfile } = await supabaseAdmin
            .from('profiles')
            .select('is_approved, membership, token_balance')
            .eq('id', userId)
            .maybeSingle()

        const updates: Record<string, unknown> = {
            is_approved: isApproved,
            signup_status: isApproved ? 'approved' : 'pending'
        }

        const wasApproved = existingProfile?.is_approved === true
        const membership = String(existingProfile?.membership || 'std').toLowerCase()
        const currentBalance = existingProfile?.token_balance || 0
        const DEFAULT_STARTER_BALANCE = 50000

        if (isApproved && !wasApproved && membership !== 'pro' && currentBalance <= DEFAULT_STARTER_BALANCE) {
            updates.token_balance = 1000000
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
