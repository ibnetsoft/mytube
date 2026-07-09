import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../../_auth'
import { getAdmin } from '../../_shared'

export const dynamic = 'force-dynamic'

// AIR-0223 withdrawal approve/reject. This is NOT new referral business logic
// — it is a TypeScript port of AIR-0221 Stage 2's
// _stage2_dual_write_withdrawal_transition (app/routers/admin_referrals.py),
// so the web admin and the desktop-app admin panel drive the exact same
// state machine and write pattern against the exact same tables. The legacy
// referral_commissions row remains the system of record (Stage 2 design,
// unchanged here) — this route updates it, then mirrors onto
// referral_withdrawals and referral_audit_logs. This is explicitly not a
// Stage 3 cutover: nothing stops writing to the legacy table.
type Transition = { status: string; auditAction: string; timestampField: string }

const APPROVE_TRANSITIONS: Transition[] = [
    { status: 'APPROVED', auditAction: 'approved', timestampField: 'approved_at' },
    { status: 'SENDING', auditAction: 'sending', timestampField: 'sent_at' },
    { status: 'COMPLETED', auditAction: 'completed', timestampField: 'completed_at' },
]
const REJECT_TRANSITIONS: Transition[] = [
    { status: 'REJECTED', auditAction: 'rejected', timestampField: 'rejected_at' },
]

export async function PATCH(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const withdrawalId = params.id
        const body = await req.json().catch(() => ({}))
        const action = body?.action as 'approve' | 'reject' | undefined
        const reason: string | undefined = body?.reason

        if (!withdrawalId || (action !== 'approve' && action !== 'reject')) {
            return NextResponse.json({ success: false, error: "Missing id or action must be 'approve'|'reject'" }, { status: 400 })
        }

        const supabase = getAdmin()

        const { data: withdrawal, error: fetchError } = await supabase
            .from('referral_withdrawals')
            .select('*')
            .eq('id', withdrawalId)
            .single()
        if (fetchError || !withdrawal) {
            return NextResponse.json({ success: false, error: 'Withdrawal not found' }, { status: 404 })
        }
        if (['COMPLETED', 'REJECTED'].includes(withdrawal.status)) {
            return NextResponse.json({ success: false, error: `Withdrawal already ${withdrawal.status}` }, { status: 400 })
        }

        const transitions = action === 'approve' ? APPROVE_TRANSITIONS : REJECT_TRANSITIONS
        const resolvedReason = reason || (action === 'approve' ? 'Approved by Admin (web)' : 'Rejected by Admin (web)')
        const legacyCommissionId: string | null = withdrawal.metadata?.legacy_commission_id || null

        // 1. Update the legacy referral_commissions row, if linked — this stays
        //    the system of record, unchanged from Stage 2's design.
        if (legacyCommissionId) {
            const { data: legacyRow, error: legacyFetchError } = await supabase
                .from('referral_commissions')
                .select('id, status, metadata')
                .eq('id', legacyCommissionId)
                .single()

            if (!legacyFetchError && legacyRow) {
                const legacyOldStatus = String(legacyRow.status || '').toUpperCase()
                const alreadyTerminal = ['COMPLETED', 'PAID', 'APPROVED', 'REJECTED', 'CANCELLED'].includes(legacyOldStatus)
                if (!alreadyTerminal || action === 'reject') {
                    const newLegacyStatus = action === 'approve' ? 'COMPLETED' : 'REJECTED'
                    const meta = legacyRow.metadata || {}
                    const auditTrail = meta.audit_trail || []
                    auditTrail.push({
                        admin: requester.user.email,
                        time: new Date().toISOString(),
                        old_status: legacyOldStatus,
                        new_status: newLegacyStatus,
                        reason: resolvedReason,
                        source: 'web_admin',
                    })
                    meta.audit_trail = auditTrail
                    const { error: legacyUpdateError } = await supabase
                        .from('referral_commissions')
                        .update({ status: newLegacyStatus, metadata: meta })
                        .eq('id', legacyCommissionId)
                    if (legacyUpdateError) {
                        console.error('[Referral Withdrawal Action] legacy update failed:', legacyUpdateError)
                    }
                }
            } else {
                console.error('[Referral Withdrawal Action] linked legacy commission not found:', legacyCommissionId)
            }
        }

        // 2. Mirror the transition sequence onto referral_withdrawals + write
        //    one referral_audit_logs row per transition.
        let updatedWithdrawal = withdrawal
        for (const t of transitions) {
            const patchPayload: Record<string, unknown> = {
                status: t.status,
                [t.timestampField]: new Date().toISOString(),
                admin_id: requester.user.id,
                reason: resolvedReason,
            }
            const { data: patched, error: patchError } = await supabase
                .from('referral_withdrawals')
                .update(patchPayload)
                .eq('id', withdrawalId)
                .select()
                .single()
            if (patchError) throw patchError
            updatedWithdrawal = patched

            const { error: auditError } = await supabase.from('referral_audit_logs').insert({
                entity_type: 'withdrawal',
                entity_id: withdrawalId,
                action: t.auditAction,
                actor_id: requester.user.id,
                reason: resolvedReason,
                metadata: {
                    legacy_commission_id: legacyCommissionId,
                    source: 'web_admin',
                },
            })
            if (auditError) {
                console.error('[Referral Withdrawal Action] audit log insert failed:', auditError)
            }
        }

        return NextResponse.json({ success: true, data: updatedWithdrawal })
    } catch (error: any) {
        console.error('[Referral Withdrawal Action] error:', error)
        return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
}
