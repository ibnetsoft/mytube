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

const DECIMAL_SCALE = 18n
const DECIMAL_FACTOR = 10n ** DECIMAL_SCALE

function decimalToUnits(value: unknown): bigint {
    const raw = String(value ?? '0').trim()
    if (!raw || raw === '.') return 0n
    const negative = raw.startsWith('-')
    const unsigned = negative ? raw.slice(1) : raw
    if (!/^\d*(\.\d*)?$/.test(unsigned)) throw new Error(`invalid_decimal:${raw}`)
    const [wholeRaw, fracRaw = ''] = unsigned.split('.')
    const whole = BigInt(wholeRaw || '0') * DECIMAL_FACTOR
    const frac = BigInt((fracRaw.slice(0, Number(DECIMAL_SCALE)).padEnd(Number(DECIMAL_SCALE), '0')) || '0')
    const units = whole + frac
    return negative ? -units : units
}

function unitsToDecimal(units: bigint): string {
    const negative = units < 0n
    const abs = negative ? -units : units
    const whole = abs / DECIMAL_FACTOR
    const frac = abs % DECIMAL_FACTOR
    const fracText = frac.toString().padStart(Number(DECIMAL_SCALE), '0').replace(/0+$/, '')
    return `${negative ? '-' : ''}${whole.toString()}${fracText ? `.${fracText}` : ''}`
}

function addDecimal(a: unknown, b: unknown): string {
    return unitsToDecimal(decimalToUnits(a) + decimalToUnits(b))
}

function subDecimal(a: unknown, b: unknown): string {
    return unitsToDecimal(decimalToUnits(a) - decimalToUnits(b))
}

function mapWalletStatus(status: string) {
    const normalized = String(status || '').toUpperCase()
    if (normalized === 'COMPLETED') return 'completed'
    if (['REJECTED', 'FAILED', 'CANCELED'].includes(normalized)) return 'rejected'
    return 'pending'
}

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
        const { data: legacyWithdrawals, error: withdrawalError } = await supabase
            .from('withdrawals')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(100)

        if (withdrawalError) throw withdrawalError

        const { data: walletWithdrawals, error: walletWithdrawalError } = await supabase
            .from('wallet_withdrawal_requests')
            .select('id,user_id,asset,network,to_address,requested_amount,fee_amount,net_amount,status,tx_hash,created_at,completed_at,rejected_at')
            .order('created_at', { ascending: false })
            .limit(100)

        if (walletWithdrawalError) throw walletWithdrawalError

        const combined: any[] = [
            ...((legacyWithdrawals || []).map((w: any) => ({
                ...w,
                source: 'legacy',
                network: w.network || 'BEP20',
                asset: 'USDT',
            }))),
            ...((walletWithdrawals || []).map((w: any) => ({
                id: `wallet:${w.id}`,
                raw_id: w.id,
                user_id: w.user_id,
                amount: Number(w.requested_amount || 0),
                dest_address: w.to_address,
                status: mapWalletStatus(w.status),
                wallet_status: w.status,
                created_at: w.created_at,
                processed_at: w.completed_at || w.rejected_at || null,
                source: 'wallet',
                asset: w.asset,
                network: w.network,
                fee_amount: Number(w.fee_amount || 0),
                net_amount: Number(w.net_amount || 0),
                tx_hash: w.tx_hash,
            }))),
        ].sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()).slice(0, 150)

        if (combined.length > 0) {
            const userIds = Array.from(new Set(combined.map(w => w.user_id).filter(Boolean)))
            const { data: profiles, error: profileError } = await supabase
                .from('profiles')
                .select('id, email')
                .in('id', userIds)

            if (!profileError && profiles) {
                const profileMap = new Map(profiles.map(p => [p.id, p]))
                combined.forEach((w: any) => {
                    const prof = profileMap.get(w.user_id)
                    w.profiles = prof ? { email: prof.email } : null
                })
            } else if (profileError) {
                console.error('Failed to join profiles on withdrawals:', profileError)
            }
        }

        return NextResponse.json({ withdrawals: combined })
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
        const idText = String(id)

        if (idText.startsWith('wallet:')) {
            const rawId = idText.replace(/^wallet:/, '')
            const { data: withdrawal, error: fetchError } = await supabase
                .from('wallet_withdrawal_requests')
                .select('*')
                .eq('id', rawId)
                .single()
            if (fetchError || !withdrawal) {
                return NextResponse.json({ error: 'Wallet withdrawal not found' }, { status: 404 })
            }
            if (['COMPLETED', 'REJECTED', 'FAILED', 'CANCELED'].includes(String(withdrawal.status || '').toUpperCase())) {
                return NextResponse.json({ success: true, data: withdrawal })
            }

            const { data: balance, error: balanceError } = await supabase
                .from('wallet_balances')
                .select('available_amount,locked_amount')
                .eq('user_id', withdrawal.user_id)
                .eq('asset', withdrawal.asset)
                .single()
            if (balanceError || !balance) throw balanceError || new Error('wallet_balance_not_found')

            const requestedAmount = String(withdrawal.requested_amount || '0')
            const nextLocked = subDecimal(balance.locked_amount || '0', requestedAmount)
            const balancePatch: any = { locked_amount: nextLocked }
            const requestPatch: any = {}
            if (status === 'completed') {
                requestPatch.status = 'COMPLETED'
                requestPatch.completed_at = new Date().toISOString()
                requestPatch.sent_at = requestPatch.completed_at
            } else {
                balancePatch.available_amount = addDecimal(balance.available_amount || '0', requestedAmount)
                requestPatch.status = 'REJECTED'
                requestPatch.rejected_at = new Date().toISOString()
            }

            const { error: updateBalanceError } = await supabase
                .from('wallet_balances')
                .update(balancePatch)
                .eq('user_id', withdrawal.user_id)
                .eq('asset', withdrawal.asset)
            if (updateBalanceError) throw updateBalanceError

            const { data: updated, error: updateRequestError } = await supabase
                .from('wallet_withdrawal_requests')
                .update(requestPatch)
                .eq('id', rawId)
                .select()
            if (updateRequestError) throw updateRequestError

            if (status === 'rejected') {
                const { error: ledgerError } = await supabase
                    .from('wallet_ledger')
                    .insert({
                        user_id: withdrawal.user_id,
                        asset: withdrawal.asset,
                        direction: 'credit',
                        amount: requestedAmount,
                        available_after: balancePatch.available_amount,
                        locked_after: nextLocked,
                        reason: 'withdrawal_reject_refund',
                        reference_type: 'wallet_withdrawal_requests',
                        reference_id: rawId,
                        idempotency_key: `wallet_withdrawal_reject_refund:${rawId}`,
                        metadata: { admin_action: 'rejected' },
                    })
                if (ledgerError && String(ledgerError.code || '') !== '23505') {
                    console.error('wallet reject refund ledger insert failed:', ledgerError)
                }
            }

            return NextResponse.json({ success: true, data: updated?.[0] || null })
        }

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
