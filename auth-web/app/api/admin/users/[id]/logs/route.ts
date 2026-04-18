import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: 특정 유저의 AI 생성 로그 조회 (어드민 전용)
export async function GET(_req: Request, { params }: { params: { id: string } }) {
    try {
        const userId = params.id
        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const supabase = getAdmin()
        const { searchParams } = new URL(_req.url)
        const days = parseInt(searchParams.get('days') || '1')
        
        // 유저 정보가 정확히 매칭되거나, 만약 유저 아이디가 없는 로그들까지 포함해서 봐야 한다면 
        // 여기서는 유저 아이디로만 필터링하지만, 대시보드 개요는 전체를 보여줍니다.
        let query = supabase
            .from('ai_logs')
            .select('*')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(1000)

        if (days > 0) {
            const date = new Date()
            date.setHours(date.getHours() - (days * 24)) // 정확히 24시간 단위
            query = query.gte('created_at', date.toISOString())
        }

        const { data, error } = await query

        if (error) throw error
        return NextResponse.json({ logs: data || [] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
