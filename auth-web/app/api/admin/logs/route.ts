import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function GET(req: Request) {
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
            .limit(2000)

        // 테이블이 없을 경우 폴백 (42P01: undefined_table)
        if (error && (error.code === '42P01' || error.code === 'PGRST116')) {
            console.warn('[Logs] ai_logs table not found, trying ai_generation_logs:', error.message)
            const fallback = await supabase
                .from('ai_generation_logs')
                .select('*')
                .gte('created_at', sinceISO)
                .order('created_at', { ascending: false })
                .limit(2000)
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
