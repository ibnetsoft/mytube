import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function GET(req: Request) {
    try {
        const supabase = getAdmin()
        const { searchParams } = new URL(req.url)
        const userId = searchParams.get('userId')

        // join이 실패할 수 있으므로 간단하게 조회 후 필터링하거나, 관계가 확실할때만 사용
        // 여기서는 안전을 위해 단순 조회를 먼저 시도합니다.
        let query = supabase
            .from('publishing_requests')
            .select('*')
            .order('created_at', { ascending: false })

        if (userId) {
            query = query.eq('user_id', userId)
        }

        const { data: requests, error } = await query
        if (error) throw error

        // 수동으로 이메일 매핑 (선택 사항 - UI에서 유저 리스트와 매칭 가능하므로 일단 단순 반환)
        return NextResponse.json({ requests: requests || [] })
    } catch (error: any) {
        console.error("Publishing API Error:", error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function PATCH(req: Request) {
    try {
        const { requestId, status } = await req.json()
        if (!requestId || !status) return NextResponse.json({ error: 'Missing parameters' }, { status: 400 })

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('publishing_requests')
            .update({ status })
            .eq('id', requestId)
            .select()

        if (error) throw error
        return NextResponse.json({ success: true, data: data[0] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
