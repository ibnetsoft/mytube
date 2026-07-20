import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: full detail + a short-lived (5 min) signed URL to view the uploaded
// evidence file. The raw storage path/public URL is never stored or
// returned unsigned - see docs/CHATGPT_PLUS_VERIFICATION_SPEC.md §4.
export async function GET(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const supabase = getAdmin()
        const { data: row, error } = await supabase
            .from('subscription_verifications')
            .select('*, profiles!subscription_verifications_user_id_fkey(email)')
            .eq('id', params.id)
            .maybeSingle()
        if (error) throw error
        if (!row) return NextResponse.json({ error: 'Not found' }, { status: 404 })

        let signedUrl: string | null = null
        if (row.storage_path) {
            const { data: signed } = await supabase.storage
                .from('subscription-verifications')
                .createSignedUrl(row.storage_path, 300)
            signedUrl = signed?.signedUrl || null
        }

        const { data: auditLog } = await supabase
            .from('subscription_verification_audit_logs')
            .select('*')
            .eq('verification_id', params.id)
            .order('created_at', { ascending: true })

        return NextResponse.json({ status: 'ok', verification: row, signed_url: signedUrl, audit_log: auditLog || [] })
    } catch (error: any) {
        console.error('[AdminSubscriptionVerificationDetail] GET Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
