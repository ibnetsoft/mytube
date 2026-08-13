import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'
import { analyzeSubscriptionScreenshot, computeVerdict, grantActiveBadge, hashEmail, maskEmail } from '@/lib/subscriptionVerification'
import { MAX_UPLOAD_SIZE_BYTES, sniffImageOrPdf } from '@/lib/uploadValidation'

export const dynamic = 'force-dynamic'

// [AIR-0228 Stage 2] User-facing submit/list endpoint for subscription
// verification uploads. Auth is the same email+session_token HMAC scheme as
// desktop-topics-bridge/desktop-drive-token (the desktop app never holds a
// raw Supabase JWT) - see lib/desktopSession.ts.
//
// Scoring/approval logic runs entirely here (server-side), never on the
// desktop app, per docs/CHATGPT_PLUS_VERIFICATION_SECURITY.md §1.

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const ALLOWED_PROVIDERS = ['chatgpt_plus', 'chatgpt_pro', 'gemini_advanced', 'claude_pro']
const APPROVED_VALIDITY_DAYS = 30

async function resolveUserId(supabase: any, email: string): Promise<string | null> {
    const { data, error } = await supabase
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data) return null
    return data.id
}

async function logAudit(supabase: any, verificationId: string, action: string, reason?: string, actorId?: string | null) {
    await supabase.from('subscription_verification_audit_logs').insert({
        verification_id: verificationId,
        action,
        actor_id: actorId || null,
        reason: reason || null,
    })
}

export async function POST(req: Request) {
    try {
        const form = await req.formData()
        const email = String(form.get('email') || '')
        const sessionToken = String(form.get('session_token') || '')
        const provider = String(form.get('provider') || '')
        const file = form.get('file') as File | null

        if (!email || !sessionToken) {
            return NextResponse.json({ status: 'error', detail: 'missing_email_or_session_token' }, { status: 401 })
        }
        if (!(await verifyApprovedDesktopSession(email, sessionToken))) {
            return NextResponse.json({ status: 'error', detail: 'invalid_or_expired_session' }, { status: 401 })
        }
        if (!ALLOWED_PROVIDERS.includes(provider)) {
            return NextResponse.json({ status: 'error', detail: 'invalid_provider' }, { status: 400 })
        }
        if (!file) {
            return NextResponse.json({ status: 'error', detail: 'missing_file' }, { status: 400 })
        }

        const arrayBuffer = await file.arrayBuffer()
        const buffer = Buffer.from(arrayBuffer)
        if (buffer.length === 0 || buffer.length > MAX_UPLOAD_SIZE_BYTES) {
            return NextResponse.json({ status: 'error', detail: 'file_too_large_or_empty' }, { status: 400 })
        }
        const sniffed = sniffImageOrPdf(buffer)
        if (!sniffed) {
            return NextResponse.json({ status: 'error', detail: 'unsupported_file_type' }, { status: 400 })
        }

        const supabase = getAdmin()
        const userId = await resolveUserId(supabase, email)
        if (!userId) {
            return NextResponse.json({ status: 'error', detail: 'profile_not_found' }, { status: 404 })
        }

        const crypto = await import('crypto')
        const fileSha256 = crypto.createHash('sha256').update(buffer).digest('hex')

        // Duplicate-image fraud signal: same file already used by a DIFFERENT user.
        const { data: dupRows } = await supabase
            .from('subscription_verifications')
            .select('id')
            .eq('file_sha256', fileSha256)
            .neq('user_id', userId)
            .limit(1)
        const duplicateImageFlag = Boolean(dupRows && dupRows.length > 0)

        const badgeCode = `${provider.toUpperCase()}_VERIFIED`

        // 1. Insert the row as UPLOADED first (preserves history even if the
        // Gemini call below fails partway through).
        const { data: inserted, error: insertError } = await supabase
            .from('subscription_verifications')
            .insert({
                user_id: userId,
                provider,
                badge_code: badgeCode,
                status: 'UPLOADED',
                storage_path: '', // filled in after upload below
                file_sha256: fileSha256,
                file_mime_type: sniffed.mimeType,
                file_size_bytes: buffer.length,
                duplicate_image_flag: duplicateImageFlag,
            })
            .select()
            .single()

        if (insertError || !inserted) {
            throw insertError || new Error('Insert returned no row')
        }
        const verificationId = inserted.id
        await logAudit(supabase, verificationId, 'uploaded')

        const storagePath = `chatgpt-plus/${userId}/${verificationId}/original.${sniffed.ext}`
        const { error: uploadError } = await supabase.storage
            .from('subscription-verifications')
            .upload(storagePath, buffer, { contentType: sniffed.mimeType, upsert: false })
        if (uploadError) {
            throw uploadError
        }
        await supabase.from('subscription_verifications').update({ storage_path: storagePath }).eq('id', verificationId)

        // 2. ANALYZING
        await supabase.from('subscription_verifications').update({ status: 'ANALYZING' }).eq('id', verificationId)
        await logAudit(supabase, verificationId, 'analysis_started')

        let finalStatus: 'APPROVED' | 'NEEDS_REVIEW' | 'REJECTED' = 'NEEDS_REVIEW'
        try {
            const analysis = await analyzeSubscriptionScreenshot(supabase, buffer, sniffed.mimeType, provider)
            const verdict = computeVerdict(analysis, duplicateImageFlag)
            finalStatus = verdict.ai_recommended_action

            const maskedEmail = maskEmail(analysis.account_email_raw)
            const emailHash = hashEmail(analysis.account_email_raw)

            const updatePayload: Record<string, unknown> = {
                document_type: analysis.document_type,
                subscription_status_raw: analysis.subscription_status_raw,
                purchase_channel: analysis.purchase_channel,
                masked_account_email: maskedEmail,
                account_email_hash: emailHash,
                payment_date: analysis.payment_date || null,
                billing_period_start: analysis.billing_period_start || null,
                billing_period_end: analysis.billing_period_end || null,
                next_renewal_date: analysis.next_renewal_date || null,
                currency: analysis.currency,
                amount: analysis.amount,
                required_fields_visible: analysis.required_fields_visible,
                ai_confidence: analysis.ai_confidence,
                ai_visual_tampering_risk: analysis.ai_visual_tampering_risk,
                ai_suspicious_reasons: analysis.ai_suspicious_reasons,
                ai_recommended_action: verdict.ai_recommended_action,
                ai_raw_response: analysis.ai_raw_response,
                rule_score: verdict.rule_score,
                status: finalStatus,
            }
            if (finalStatus === 'APPROVED') {
                const expiresAt = new Date(Date.now() + APPROVED_VALIDITY_DAYS * 24 * 60 * 60 * 1000).toISOString()
                updatePayload.expires_at = expiresAt
            }

            await supabase.from('subscription_verifications').update(updatePayload).eq('id', verificationId)
            await logAudit(
                supabase,
                verificationId,
                finalStatus === 'APPROVED' ? 'auto_approved' : finalStatus === 'REJECTED' ? 'rejected' : 'sent_to_review'
            )

            if (finalStatus === 'APPROVED') {
                await grantActiveBadge(supabase, userId, badgeCode, verificationId, (updatePayload.expires_at as string) || null)
            }
        } catch (analysisError: any) {
            console.error('[SubscriptionVerification] Analysis failed:', analysisError?.message)
            await supabase
                .from('subscription_verifications')
                .update({ status: 'NEEDS_REVIEW', rejection_reason: `analysis_error: ${analysisError?.message || 'unknown'}` })
                .eq('id', verificationId)
            await logAudit(supabase, verificationId, 'sent_to_review', 'analysis_error')
            finalStatus = 'NEEDS_REVIEW'
        }

        return NextResponse.json({ status: 'ok', verification_id: verificationId, result_status: finalStatus })
    } catch (error: any) {
        console.error('[SubscriptionVerifications] POST Error:', error?.message)
        return NextResponse.json({ status: 'error', detail: 'internal_error' }, { status: 500 })
    }
}

export async function GET(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const email = searchParams.get('email') || ''
        const sessionToken = searchParams.get('session_token') || ''
        const provider = searchParams.get('provider') || ''

        if (!email || !sessionToken) {
            return NextResponse.json({ status: 'error', detail: 'missing_email_or_session_token' }, { status: 401 })
        }
        if (!(await verifyApprovedDesktopSession(email, sessionToken))) {
            return NextResponse.json({ status: 'error', detail: 'invalid_or_expired_session' }, { status: 401 })
        }

        const supabase = getAdmin()
        const userId = await resolveUserId(supabase, email)
        if (!userId) {
            return NextResponse.json({ status: 'error', detail: 'profile_not_found' }, { status: 404 })
        }

        let query = supabase
            .from('subscription_verifications')
            .select('id, provider, status, rule_score, ai_recommended_action, rejection_reason, expires_at, created_at, updated_at')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })

        if (provider) query = query.eq('provider', provider)

        const { data, error } = await query
        if (error) throw error

        return NextResponse.json({ status: 'ok', rows: data || [] })
    } catch (error: any) {
        console.error('[SubscriptionVerifications] GET Error:', error?.message)
        return NextResponse.json({ status: 'error', detail: 'internal_error' }, { status: 500 })
    }
}
