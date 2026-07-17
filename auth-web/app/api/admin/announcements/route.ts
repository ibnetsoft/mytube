import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// GET: 어드민 화면용 전체 목록 (초안 포함)
export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('announcements')
            .select('*, author:profiles!announcements_created_by_fkey(email)')
            .order('is_pinned', { ascending: false })
            .order('created_at', { ascending: false })

        if (error) throw error
        return NextResponse.json({ status: 'ok', rows: data || [] })
    } catch (error: any) {
        console.error('[AdminAnnouncements] GET Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

// POST: 새 공지 작성. is_published 기본값 true(즉시 게시) - 초안으로 두려면
// 요청에 is_published: false 를 명시.
export async function POST(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { title, body, is_pinned, is_published } = await req.json()
        const cleanTitle = String(title || '').trim().slice(0, 200)
        const cleanBody = String(body || '').trim().slice(0, 10000)
        if (!cleanTitle || !cleanBody) {
            return NextResponse.json({ error: 'title and body are required' }, { status: 400 })
        }

        const published = is_published !== false
        const pinned = !!is_pinned
        const now = new Date().toISOString()

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('announcements')
            .insert({
                title: cleanTitle,
                body: cleanBody,
                is_pinned: pinned,
                is_published: published,
                pinned_at: pinned ? now : null,
                published_at: published ? now : null,
                created_by: requester.user.id,
                updated_by: requester.user.id,
            })
            .select('id')
            .maybeSingle()

        if (error) throw error
        return NextResponse.json({ status: 'ok', id: data?.id })
    } catch (error: any) {
        console.error('[AdminAnnouncements] POST Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
