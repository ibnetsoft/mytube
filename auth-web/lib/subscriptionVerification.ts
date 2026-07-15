import crypto from 'crypto'
import { GoogleGenAI } from '@google/genai'

// [AIR-0228 Stage 2] Gemini Vision analysis + rule scoring for subscription
// verification screenshots. Runs server-side (auth-web) only - the desktop
// app is not a trusted execution environment for this judgment
// (docs/CHATGPT_PLUS_VERIFICATION_SECURITY.md §1), so no scoring/approval
// logic exists on the Python side; it only proxies the raw file here.

export type AnalysisResult = {
    document_type: string | null
    subscription_status_raw: string | null
    purchase_channel: string | null
    account_email_raw: string | null
    payment_date: string | null
    billing_period_start: string | null
    billing_period_end: string | null
    next_renewal_date: string | null
    currency: string | null
    amount: number | null
    required_fields_visible: boolean
    ai_confidence: number
    ai_visual_tampering_risk: 'low' | 'medium' | 'high'
    ai_suspicious_reasons: string[]
    ai_raw_response: unknown
}

const RESPONSE_SCHEMA = {
    type: 'object',
    properties: {
        document_type: { type: 'string', description: 'e.g. "chatgpt_plus_receipt", "chatgpt_plus_settings_screen", "unrelated", "unreadable"' },
        subscription_status_raw: { type: 'string', description: 'active/canceled/expired/unknown, as literally shown' },
        purchase_channel: { type: 'string', description: 'e.g. "web", "ios_app_store", "android_play_store", "unknown"' },
        account_email_raw: { type: 'string', description: 'The account email exactly as shown in the image, or empty string if not visible' },
        payment_date: { type: 'string', description: 'ISO 8601 date (YYYY-MM-DD) if visible, else empty string' },
        billing_period_start: { type: 'string', description: 'ISO 8601 date if visible, else empty string' },
        billing_period_end: { type: 'string', description: 'ISO 8601 date if visible, else empty string' },
        next_renewal_date: { type: 'string', description: 'ISO 8601 date if visible, else empty string' },
        currency: { type: 'string', description: 'ISO 4217 currency code (e.g. USD) if visible, else empty string' },
        amount: { type: 'number', description: 'Numeric amount charged, 0 if not visible' },
        required_fields_visible: { type: 'boolean', description: 'true only if this clearly shows an active ChatGPT Plus subscription with account email AND (payment date OR next renewal date) visible' },
        ai_confidence: { type: 'number', description: '0.0 to 1.0 - how confident you are this is a genuine, unedited ChatGPT Plus subscription screenshot/receipt' },
        ai_visual_tampering_risk: { type: 'string', enum: ['low', 'medium', 'high'], description: 'Visual signs of editing/tampering (inconsistent fonts, misaligned text, pixelation around numbers, mismatched UI chrome, etc.)' },
        ai_suspicious_reasons: { type: 'array', items: { type: 'string' }, description: 'Empty array if nothing suspicious. Otherwise short specific reasons.' },
    },
    required: [
        'document_type', 'subscription_status_raw', 'purchase_channel', 'account_email_raw',
        'payment_date', 'billing_period_start', 'billing_period_end', 'next_renewal_date',
        'currency', 'amount', 'required_fields_visible', 'ai_confidence',
        'ai_visual_tampering_risk', 'ai_suspicious_reasons',
    ],
}

function buildPrompt(provider: string): string {
    return `You are a fraud-detection assistant reviewing a screenshot a user submitted as proof of an active "${provider}" subscription (e.g. ChatGPT Plus).

Carefully examine the image for:
1. Whether it genuinely shows an active subscription to this specific service (not a different service, not a mockup, not a generic screenshot).
2. Visual signs of digital editing/tampering: inconsistent fonts or sizes, misaligned text, pixelation or blurring around numbers/dates/amounts, mismatched UI chrome vs. the claimed app/website, inconsistent shadows or anti-aliasing around edited regions.
3. Extract every field in the response schema exactly as shown in the image. If a field is not visible, use an empty string (or 0 for amount, false for booleans as appropriate) - do not guess or fabricate values.
4. Be conservative: if you are not confident this is a genuine subscription confirmation for this exact service, set ai_confidence low and list your concerns in ai_suspicious_reasons.

Respond only with the JSON matching the provided schema.`
}

async function getGeminiApiKey(supabaseAdmin: any): Promise<string> {
    let key = process.env.GEMINI_API_KEY
    if (!key) {
        const { data } = await supabaseAdmin
            .from('global_settings')
            .select('value')
            .eq('key', 'sys_api_gemini')
            .maybeSingle()
        key = data?.value
    }
    if (!key) throw new Error('Gemini API key is not configured')
    return key
}

export async function analyzeSubscriptionScreenshot(
    supabaseAdmin: any,
    imageBuffer: Buffer,
    mimeType: string,
    provider: string
): Promise<AnalysisResult> {
    const apiKey = await getGeminiApiKey(supabaseAdmin)
    const ai = new GoogleGenAI({ apiKey })

    const response = await ai.models.generateContent({
        model: 'gemini-2.5-flash',
        contents: [
            {
                role: 'user',
                parts: [
                    { inlineData: { data: imageBuffer.toString('base64'), mimeType } },
                    { text: buildPrompt(provider) },
                ],
            },
        ],
        config: {
            responseMimeType: 'application/json',
            responseSchema: RESPONSE_SCHEMA as any,
        },
    })

    let parsed: any
    try {
        parsed = JSON.parse(response.text || '{}')
    } catch {
        // Fallback: this repo's standard pattern elsewhere (services/gemini_service.py)
        // is regex-extract a {...} blob when the model doesn't return clean JSON.
        const match = (response.text || '').match(/\{[\s\S]*\}/)
        parsed = match ? JSON.parse(match[0]) : {}
    }

    return {
        document_type: parsed.document_type || null,
        subscription_status_raw: parsed.subscription_status_raw || null,
        purchase_channel: parsed.purchase_channel || null,
        account_email_raw: parsed.account_email_raw || null,
        payment_date: parsed.payment_date || null,
        billing_period_start: parsed.billing_period_start || null,
        billing_period_end: parsed.billing_period_end || null,
        next_renewal_date: parsed.next_renewal_date || null,
        currency: parsed.currency || null,
        amount: typeof parsed.amount === 'number' ? parsed.amount : null,
        required_fields_visible: Boolean(parsed.required_fields_visible),
        ai_confidence: typeof parsed.ai_confidence === 'number' ? parsed.ai_confidence : 0,
        ai_visual_tampering_risk: ['low', 'medium', 'high'].includes(parsed.ai_visual_tampering_risk)
            ? parsed.ai_visual_tampering_risk
            : 'high',
        ai_suspicious_reasons: Array.isArray(parsed.ai_suspicious_reasons) ? parsed.ai_suspicious_reasons : [],
        ai_raw_response: parsed,
    }
}

export function maskEmail(email: string | null): string | null {
    if (!email) return null
    const [local, domain] = email.split('@')
    if (!domain) return null
    const visible = local.slice(0, Math.min(2, local.length))
    return `${visible}${'*'.repeat(Math.max(local.length - visible.length, 1))}@${domain}`
}

export function hashEmail(email: string | null): string | null {
    if (!email) return null
    const normalized = email.trim().toLowerCase()
    return crypto.createHash('sha256').update(normalized).digest('hex')
}

// SPEC §2 state machine decision rule.
export function computeVerdict(
    analysis: AnalysisResult,
    duplicateImageFlag: boolean
): { rule_score: number; ai_recommended_action: 'APPROVED' | 'NEEDS_REVIEW' | 'REJECTED' } {
    let score = analysis.ai_confidence * 100

    if (!analysis.required_fields_visible) score -= 30
    if (analysis.ai_visual_tampering_risk === 'medium') score -= 20
    if (analysis.ai_visual_tampering_risk === 'high') score -= 60
    if (analysis.ai_suspicious_reasons.length > 0) score -= 10 * analysis.ai_suspicious_reasons.length
    if (duplicateImageFlag) score = Math.min(score, 50) // never auto-approve a reused image

    score = Math.max(0, Math.min(100, score))

    let action: 'APPROVED' | 'NEEDS_REVIEW' | 'REJECTED'
    if (analysis.ai_visual_tampering_risk === 'high' || analysis.document_type === 'unrelated') {
        action = 'REJECTED'
    } else if (score >= 95 && analysis.required_fields_visible && !duplicateImageFlag) {
        action = 'APPROVED'
    } else {
        action = 'NEEDS_REVIEW'
    }

    return { rule_score: Math.round(score * 100) / 100, ai_recommended_action: action }
}

// [AIR-0228] Deliberately NOT a `.upsert(..., { onConflict: 'user_id,badge_code' })`
// call: user_badges.uq_user_badges_active_per_code is a PARTIAL unique index
// (WHERE status = 'ACTIVE'), not a plain unique constraint on those two
// columns - by design, so a user can keep historical EXPIRED/REVOKED rows for
// the same badge_code across multiple grant cycles. Postgres/PostgREST can't
// use a partial index as an ON CONFLICT arbiter for a plain column-list
// target, so this does the check-then-insert-or-update explicitly instead.
export async function grantActiveBadge(
    supabase: any,
    userId: string,
    badgeCode: string,
    sourceId: string,
    expiresAt: string | null
): Promise<void> {
    const { data: existing } = await supabase
        .from('user_badges')
        .select('id')
        .eq('user_id', userId)
        .eq('badge_code', badgeCode)
        .eq('status', 'ACTIVE')
        .maybeSingle()

    if (existing) {
        const { error } = await supabase
            .from('user_badges')
            .update({ source_id: sourceId, granted_at: new Date().toISOString(), expires_at: expiresAt })
            .eq('id', existing.id)
        if (error) throw error
    } else {
        const { error } = await supabase.from('user_badges').insert({
            user_id: userId,
            badge_code: badgeCode,
            source_type: 'subscription_verification',
            source_id: sourceId,
            status: 'ACTIVE',
            granted_at: new Date().toISOString(),
            expires_at: expiresAt,
        })
        if (error) throw error
    }
}
