import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../_auth'
import { translateAndSaveAnnouncement } from '../_shared'

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

        const nextTitle = typeof body.title === 'string' ? body.title.trim().slice(0, 200) : undefined
        const nextBody = typeof body.body === 'string' ? body.body.trim().slice(0, 10000) : undefined
        if (nextTitle !== undefined) updates.title = nextTitle
        if (nextBody !== undefined) updates.body = nextBody
        if (typeof body.is_pinned === 'boolean') {
            updates.is_pinned = body.is_pinned
            updates.pinned_at = body.is_pinned ? now : null
        }
        if (typeof body.is_published === 'boolean') {
            updates.is_published = body.is_published
            if (body.is_published) updates.published_at = now
        }

        const supabase = getAdmin()

        // AIR-0229: title/body가 바뀌면 en/vi/th 번역이 원문과 어긋나므로 다시
        // 번역해야 한다 - 기존 값과 비교하기 위해 갱신 전에 한 번 읽는다.
        let contentChanged = false
        if (nextTitle !== undefined || nextBody !== undefined) {
            const { data: existing } = await supabase
                .from('announcements')
                .select('title, body')
                .eq('id', params.id)
                .maybeSingle()
            if (existing) {
                contentChanged = (nextTitle !== undefined && nextTitle !== existing.title) ||
                    (nextBody !== undefined && nextBody !== existing.body)
            }
        }
        if (contentChanged) updates.translation_status = 'pending'

        const { data, error } = await supabase
            .from('announcements')
            .update(updates)
            .eq('id', params.id)
            .select('id, title, body')
            .maybeSingle()

        if (error) throw error
        if (!data) return NextResponse.json({ error: 'Announcement not found' }, { status: 404 })

        if (contentChanged) {
            await translateAndSaveAnnouncement(data.id, data.title, data.body, supabase)
        }

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
