import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { requireAdmin, isAuthResponse } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const LOG_LIST_SELECT = `
    id,
    user_id,
    task_type,
    model_id,
    provider,
    status,
    prompt_summary,
    error_msg,
    elapsed_time,
    created_at,
    input_tokens,
    output_tokens,
    thinking_tokens,
    balance_after,
    worker_email
`

// [AIR-0227D-VALIDATION additional static check 3 - security hotfix] had no
// admin auth check at all - found during the full /api/admin/** audit.
export async function GET(req: Request) {
    const requester = await requireAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { searchParams } = new URL(req.url)
        const days = parseInt(searchParams.get('days') || '1')
        const requestedLimit = parseInt(searchParams.get('limit') || '2000')
        const limit = Math.max(100, Math.min(5000, Number.isFinite(requestedLimit) ? requestedLimit : 2000))

        const since = new Date()
        since.setDate(since.getDate() - days)
        const sinceISO = since.toISOString()

        const supabase = getAdmin()

        let { data, error } = await supabase
            .from('ai_logs')
            .select(LOG_LIST_SELECT)
            .gte('created_at', sinceISO)
            .order('created_at', { ascending: false })
            // Keep the dashboard responsive and prevent Supabase egress spikes.
            // Accurate long-range accounting should use the daily rollup endpoint.
            .limit(limit)

        // 테이블이 없을 경우 폴백 (42P01: undefined_table)
        if (error && (error.code === '42P01' || error.code === 'PGRST116')) {
            console.warn('[Logs] ai_logs table not found, trying ai_generation_logs:', error.message)
            const fallback = await supabase
                .from('ai_generation_logs')
                .select(LOG_LIST_SELECT)
                .gte('created_at', sinceISO)
                .order('created_at', { ascending: false })
                .limit(limit)
            data = fallback.data
            error = fallback.error
        }

        if (error) {
            console.error('[Logs] Query error:', error)
            throw error
        }
        console.log(`[Logs] Fetched ${data?.length || 0} logs for last ${days} days`)
        return NextResponse.json({ logs: data || [] })
    } catch (error: any) {
        console.error("Logs API Error:", error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
