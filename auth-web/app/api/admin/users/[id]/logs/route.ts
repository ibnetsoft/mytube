import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 특정 유저의 AI 생성 로그 조회 (어드민 전용)
export async function GET(_req: Request, { params }: { params: { id: string } }) {
    try {
        const userId = params.id
        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const { data, error } = await getAdmin()
            .from('ai_logs')
            .select('*')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(200)

        if (error) throw error
        return NextResponse.json({ logs: data || [] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
