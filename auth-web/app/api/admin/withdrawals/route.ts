import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

// [AIR-0227D-SECURITY-HOTFIX Stage 2 - role-level upgrade, not just an auth
// gap] this route already had requireAdmin (sub_admin-eligible) on both
// GET and PATCH, so it wasn't in the "zero auth" list - but PATCH approves
// or rejects real USDT withdrawal requests and triggers commission
// calculation, the same severity class as the already-requireSuperAdmin
// admin/settlements/payout route. Upgraded both to requireSuperAdmin for
// consistency with that sibling. This is a real behavior change: any
// sub_admin currently relying on this to process withdrawals will need to
// be re-provisioned as a super admin, or this reverted, if that workflow
// is in active use - flagged in the hotfix report rather than silently
// applied.

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// AIR-0221A hotfix: process_withdrawal_commission RPC was dropped in production
// (migrations/air_0158c) but this route still called it. Reimplemented inline
// using calculate_commission (still live) + direct UPDATE/INSERT, same behavior
// and same tenant_commission_logs side effect as the original RPC.
async function processWithdrawalCommission(
    supabase: ReturnType<typeof getAdmin>,
    withdrawalId: string
): Promise<{ success: boolean; error?: string; commission_percent?: number; commission_usd?: number; net_usd?: number; tenant_key?: string; log_id?: string }> {
    const { data: withdrawal, error: fetchError } = await supabase
        .from('withdrawals')
        .select('*')
        .eq('id', withdrawalId)
        .single()

    if (fetchError || !withdrawal) {
        return { success: false, error: 'withdrawal_not_found' }
    }

    const { data: commissionResult, error: commissionError } = await supabase
        .rpc('calculate_commission', {
            p_user_id: withdrawal.user_id,
            p_amount_usd: withdrawal.amount
        })

    if (commissionError || !commissionResult || commissionResult.success !== true) {
        return { success: false, error: commissionError?.message || commissionResult?.error || 'calculate_commission_failed' }
    }

    const commission_percent = commissionResult.commission_percent
    const commission_usd = commissionResult.commission_usd
    const net_usd = commissionResult.net_usd
    const tenant_key = commissionResult.tenant_key

    const { error: updateError } = await supabase
        .from('withdrawals')
        .update({ commission_percent, commission_usd, net_usd, tenant_key })
        .eq('id', withdrawalId)

    if (updateError) {
        return { success: false, error: updateError.message }
    }

    let log_id: string | undefined
    if (withdrawal.status === 'pending' || withdrawal.status === 'completed') {
        const { data: logRow, error: logError } = await supabase
            .from('tenant_commission_logs')
            .insert({
                tenant_key,
                user_id: withdrawal.user_id,
                transaction_type: 'commission',
                amount_usd: withdrawal.amount,
                commission_percent,
                commission_usd,
                net_usd,
                transaction_id: withdrawalId,
                metadata: withdrawal.status === 'pending'
                    ? { withdrawal_id: withdrawalId, pending: true }
                    : { withdrawal_id: withdrawalId, completed: true }
            })
            .select('id')
            .single()

        if (logError) {
            console.error('tenant_commission_logs insert failed:', logError)
        } else {
            log_id = logRow?.id
        }
    }

    return { success: true, commission_percent, commission_usd, net_usd, tenant_key, log_id }
}

// GET: 출금 요청 목록 조회 (profiles 이메일 정보 병합)
export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
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
        const requester = await requireSuperAdmin(req)
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

        // 수수료 계산 (구 process_withdrawal_commission RPC 대체 — AIR-0221A)
        const commissionResult = await processWithdrawalCommission(supabase, id)

        if (!commissionResult.success) {
            console.error('Commission calculation failed:', commissionResult.error)
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
