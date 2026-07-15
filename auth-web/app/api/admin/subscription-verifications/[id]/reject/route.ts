import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function POST(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json().catch(() => ({}))
        const reason = String(body?.reason || '').trim() || null

        const supabase = getAdmin()
        const { data: row, error: fetchError } = await supabase
            .from('subscription_verifications')
            .select('id, user_id, badge_code')
            .eq('id', params.id)
            .maybeSingle()
        if (fetchError) throw fetchError
        if (!row) return NextResponse.json({ error: 'Not found' }, { status: 404 })

        const { error: updateError } = await supabase
            .from('subscription_verifications')
            .update({
                status: 'REJECTED',
                reviewed_by: requester.user.id,
                reviewed_at: new Date().toISOString(),
                rejection_reason: reason,
            })
            .eq('id', params.id)
        if (updateError) throw updateError

        // If this verification had previously granted an ACTIVE badge (e.g. a
        // re-review overturning an earlier auto-approval), revoke it.
        await supabase
            .from('user_badges')
            .update({ status: 'REVOKED', revoked_at: new Date().toISOString() })
            .eq('user_id', row.user_id)
            .eq('badge_code', row.badge_code)
            .eq('source_id', row.id)
            .eq('status', 'ACTIVE')

        await supabase.from('subscription_verification_audit_logs').insert({
            verification_id: params.id,
            action: 'rejected',
            actor_id: requester.user.id,
            reason,
        })

        return NextResponse.json({ status: 'ok' })
    } catch (error: any) {
        console.error('[AdminSubscriptionVerificationReject] Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
