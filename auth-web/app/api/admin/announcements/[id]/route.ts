import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// PATCH: 제목/본문 수정, 고정(is_pinned) 토글, 발행(is_published) 토글을
// 한 엔드포인트에서 처리한다 - 요청에 담긴 필드만 갱신.
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const updates: Record<string, unknown> = { updated_by: requester.user.id, updated_at: new Date().toISOString() }
        const now = new Date().toISOString()

        if (typeof body.title === 'string') updates.title = body.title.trim().slice(0, 200)
        if (typeof body.body === 'string') updates.body = body.body.trim().slice(0, 10000)
        if (typeof body.is_pinned === 'boolean') {
            updates.is_pinned = body.is_pinned
            updates.pinned_at = body.is_pinned ? now : null
        }
        if (typeof body.is_published === 'boolean') {
            updates.is_published = body.is_published
            if (body.is_published) updates.published_at = now
        }

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('announcements')
            .update(updates)
            .eq('id', params.id)
            .select('id')
            .maybeSingle()

        if (error) throw error
        if (!data) return NextResponse.json({ error: 'Announcement not found' }, { status: 404 })

        return NextResponse.json({ status: 'ok' })
    } catch (error: any) {
        console.error('[AdminAnnouncements] PATCH Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

// DELETE: 공지 삭제
export async function DELETE(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const supabase = getAdmin()
        const { error } = await supabase
            .from('announcements')
            .delete()
            .eq('id', params.id)

        if (error) throw error
        return NextResponse.json({ status: 'ok' })
    } catch (error: any) {
        console.error('[AdminAnnouncements] DELETE Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
