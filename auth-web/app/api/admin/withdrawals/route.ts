import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: 출금 요청 목록 조회 (profiles 이메일 정보 병합)
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const supabase = getAdmin()
        const { data: withdrawals, error: withdrawalError } = await supabase
            .from('withdrawals')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(100)

        if (withdrawalError) throw withdrawalError

        if (withdrawals && withdrawals.length > 0) {
            const userIds = Array.from(new Set(withdrawals.map(w => w.user_id)))
            const { data: profiles, error: profileError } = await supabase
                .from('profiles')
                .select('id, email')
                .in('id', userIds)

            if (!profileError && profiles) {
                const profileMap = new Map(profiles.map(p => [p.id, p]))
                withdrawals.forEach((w: any) => {
                    const prof = profileMap.get(w.user_id)
                    w.profiles = prof ? { email: prof.email } : null
                })
            } else if (profileError) {
                console.error('Failed to join profiles on withdrawals:', profileError)
            }
        }

        return NextResponse.json({ withdrawals: withdrawals || [] })
    } catch (e: any) {
        console.error('Failed to get withdrawals:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PATCH: 출금 요청 상태 업데이트 (승인/거절) + 수수료 계산
export async function PATCH(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const { id, status } = body

        if (!id || !['completed', 'rejected'].includes(status)) {
            return NextResponse.json({ error: 'Invalid parameters' }, { status: 400 })
        }

        const supabase = getAdmin()

        // 거절인 경우 상태만 업데이트
        if (status === 'rejected') {
            const { data, error } = await supabase
                .from('withdrawals')
                .update({
                    status,
                    processed_at: new Date().toISOString()
                })
                .eq('id', id)
                .select()

            if (error) throw error
            return NextResponse.json({ success: true, data: data?.[0] || null })
        }

        // 완료인 경우 수수료 계산
        const { data: withdrawal } = await supabase
            .from('withdrawals')
            .select('*')
            .eq('id', id)
            .single()

        if (!withdrawal) {
            return NextResponse.json({ error: 'Withdrawal not found' }, { status: 404 })
        }

        // 수수료 계산 함수 호출
        const { data: commissionResult, error: commissionError } = await supabase
            .rpc('process_withdrawal_commission', { p_withdrawal_id: id })

        if (commissionError) {
            console.error('Commission calculation failed:', commissionError)
            // 수수료 계산 실패해도 출금은 완료 처리
        }

        // 출금 상태 업데이트
        const { data: updated, error: updateError } = await supabase
            .from('withdrawals')
            .update({
                status,
                processed_at: new Date().toISOString(),
                ...(commissionResult?.commission_percent !== undefined && {
                    commission_percent: commissionResult.commission_percent,
                    commission_usd: commissionResult.commission_usd,
                    net_usd: commissionResult.net_usd,
                    tenant_key: commissionResult.tenant_key
                })
            })
            .eq('id', id)
            .select()

        if (updateError) throw updateError

        return NextResponse.json({
            success: true,
            data: updated?.[0] || null,
            commission: commissionResult
        })
    } catch (e: any) {
        console.error('Failed to update withdrawal status:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
