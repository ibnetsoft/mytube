import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { requireAdmin, isAuthResponse } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// [AIR-0227D-VALIDATION additional static check 3 - security hotfix] had no
// admin auth check at all - found during the full /api/admin/** audit.
export async function GET(req: Request) {
    const requester = await requireAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { searchParams } = new URL(req.url)
        const days = parseInt(searchParams.get('days') || '1')

        const since = new Date()
        since.setDate(since.getDate() - days)
        const sinceISO = since.toISOString()

        const supabase = getAdmin()

        let { data, error } = await supabase
            .from('ai_logs')
            .select('*')
            .gte('created_at', sinceISO)
            .order('created_at', { ascending: false })
            // [AIR-0230] 2000건 하드캡은 활동이 많은 달에는 실제 사용량의 일부만
            // 반영해 비용 집계가 부정확해질 수 있었다. 20000으로 상향 - 이 이상
            // 커지면 클라이언트 집계 대신 Postgres RPC 기반 서버사이드 집계로
            // 전환이 필요하다(범위 밖, 다음 단계로 남겨둠).
            .limit(20000)

        // 테이블이 없을 경우 폴백 (42P01: undefined_table)
        if (error && (error.code === '42P01' || error.code === 'PGRST116')) {
            console.warn('[Logs] ai_logs table not found, trying ai_generation_logs:', error.message)
            const fallback = await supabase
                .from('ai_generation_logs')
                .select('*')
                .gte('created_at', sinceISO)
                .order('created_at', { ascending: false })
                // [AIR-0230] 2000건 하드캡은 활동이 많은 달에는 실제 사용량의 일부만
            // 반영해 비용 집계가 부정확해질 수 있었다. 20000으로 상향 - 이 이상
            // 커지면 클라이언트 집계 대신 Postgres RPC 기반 서버사이드 집계로
            // 전환이 필요하다(범위 밖, 다음 단계로 남겨둠).
            .limit(20000)
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
