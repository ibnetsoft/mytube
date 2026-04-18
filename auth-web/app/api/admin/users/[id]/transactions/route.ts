import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: 특정 유저의 토큰 트랜잭션 내역 조회 (어드민 전용)
export async function GET(_req: Request, { params }: { params: { id: string } }) {
    try {
        const userId = params.id
        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const { searchParams } = new URL(_req.url)
        const limit = parseInt(searchParams.get('limit') || '50')

        const { data, error } = await getAdmin()
            .from('token_transactions')
            .select('*')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(limit)

        if (error) throw error
        return NextResponse.json({ transactions: data || [] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
