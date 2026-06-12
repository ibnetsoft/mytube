import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 렌더링 대기열 전체 목록 조회
export async function GET() {
    try {
        const sb = getAdmin()
        const { data, error } = await sb
            .from('remote_render_queue')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(100)
            
        if (error) throw error
        return NextResponse.json({ success: true, queue: data || [] })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 특정 렌더링 작업 삭제/취소
export async function DELETE(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const id = searchParams.get('id')
        if (!id) return NextResponse.json({ error: 'Missing id' }, { status: 400 })

        const sb = getAdmin()
        const { error } = await sb
            .from('remote_render_queue')
            .delete()
            .eq('id', id)
            
        if (error) throw error
        return NextResponse.json({ success: true })
    } catch (e: any) {
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
