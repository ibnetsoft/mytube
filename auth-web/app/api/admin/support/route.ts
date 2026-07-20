import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: 문의 목록 - 발신자 프로필(email) 조인, AI 초안 포함(어드민만 봄).
// 서브어드민도 문의 응대는 가능하도록 requireAdmin(수퍼어드민 한정 아님).
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const status = searchParams.get('status')
        const limit = Math.min(Math.max(Number(searchParams.get('limit')) || 50, 1), 200)

        const supabase = getAdmin()
        let query = supabase
            .from('support_messages')
            .select('*, profiles!support_messages_user_id_fkey(email, full_name)')
            .order('created_at', { ascending: false })
            .limit(limit)

        if (status) query = query.eq('status', status)

        const { data, error } = await query
        if (error) throw error

        return NextResponse.json({ status: 'ok', rows: data || [] })
    } catch (error: any) {
        console.error('[AdminSupport] GET Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
