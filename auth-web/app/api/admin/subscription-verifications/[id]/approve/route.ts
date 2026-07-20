import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../../../_auth'
import { grantActiveBadge } from '@/lib/subscriptionVerification'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const APPROVED_VALIDITY_DAYS = 30

export async function POST(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const supabase = getAdmin()
        const { data: row, error: fetchError } = await supabase
            .from('subscription_verifications')
            .select('id, user_id, badge_code, status')
            .eq('id', params.id)
            .maybeSingle()
        if (fetchError) throw fetchError
        if (!row) return NextResponse.json({ error: 'Not found' }, { status: 404 })
        if (row.status === 'APPROVED') {
            return NextResponse.json({ status: 'ok', already_approved: true })
        }

        const expiresAt = new Date(Date.now() + APPROVED_VALIDITY_DAYS * 24 * 60 * 60 * 1000).toISOString()

        const { error: updateError } = await supabase
            .from('subscription_verifications')
            .update({ status: 'APPROVED', reviewed_by: requester.user.id, reviewed_at: new Date().toISOString(), expires_at: expiresAt })
            .eq('id', params.id)
        if (updateError) throw updateError

        await grantActiveBadge(supabase, row.user_id, row.badge_code, row.id, expiresAt)

        await supabase.from('subscription_verification_audit_logs').insert({
            verification_id: params.id,
            action: 'approved',
            actor_id: requester.user.id,
        })

        return NextResponse.json({ status: 'ok' })
    } catch (error: any) {
        console.error('[AdminSubscriptionVerificationApprove] Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
