import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

const TABLE = 'remote_render_queue'
const MAX_LIST_LIMIT = 200

// [AIR-0225B] Bridges services/remote_drive_render_service.py's
// remote_render_queue reads/writes (STD-tier "그래픽서버" cloud rendering).
// That service used to hit Supabase directly with SUPABASE_SERVICE_ROLE_KEY,
// a key that was intentionally removed from the desktop package after the
// 2026-07-11 leak remediation (worker/build_windows.ps1 now refuses to write
// it into the packaged .env) - which silently broke remote rendering for
// every STD-tier user, since local rendering isn't offered to that tier at
// all. This route re-does those operations server-side, gated by the same
// signed session_token scheme /api/desktop-resync already uses (a bare email
// is never sufficient - see lib/desktopSession.ts).
//
// This intentionally does NOT scope GET results to the caller's own email:
// list_queue_rows() was already a company-wide view (any employee's session
// could see any other's pending jobs via the raw Supabase call this
// replaces) - matching that existing behavior, not narrowing or widening it.

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { email, session_token, payload } = body || {}

        if (!email || !session_token) {
            return NextResponse.json({ success: false, error: 'Missing email or session_token' }, { status: 400 })
        }
        if (!verifyDesktopSessionToken(String(email), String(session_token))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
            return NextResponse.json({ success: false, error: 'Missing payload' }, { status: 400 })
        }

        const { data, error } = await supabaseAdmin
            .from(TABLE)
            .insert(payload)
            .select()
            .single()

        if (error) {
            console.error('[DesktopRenderQueue] insert error:', error.message)
            return NextResponse.json({ success: false, error: error.message }, { status: 500 })
        }
        return NextResponse.json({ success: true, row: data })
    } catch (error: any) {
        console.error('[DesktopRenderQueue] POST error:', error?.message)
        return NextResponse.json({ success: false, error: '서버 오류' }, { status: 500 })
    }
}

export async function GET(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const email = searchParams.get('email') || ''
        const sessionToken = searchParams.get('session_token') || ''
        const taskId = searchParams.get('task_id')
        const statusesRaw = searchParams.get('statuses')
        const limitRaw = searchParams.get('limit')

        if (!email || !sessionToken) {
            return NextResponse.json({ success: false, error: 'Missing email or session_token' }, { status: 400 })
        }
        if (!verifyDesktopSessionToken(email, sessionToken)) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        if (taskId) {
            const { data, error } = await supabaseAdmin
                .from(TABLE)
                .select('*')
                .eq('id', taskId)
                .limit(1)
                .maybeSingle()
            if (error) {
                console.error('[DesktopRenderQueue] get-by-id error:', error.message)
                return NextResponse.json({ success: false, error: error.message }, { status: 500 })
            }
            return NextResponse.json({ success: true, row: data || null })
        }

        const limit = Math.min(MAX_LIST_LIMIT, Math.max(1, parseInt(limitRaw || '50', 10) || 50))
        let query = supabaseAdmin
            .from(TABLE)
            .select('*')
            .order('updated_at', { ascending: false })
            .limit(limit)

        if (statusesRaw) {
            const statuses = statusesRaw.split(',').map((s) => s.trim()).filter(Boolean)
            if (statuses.length) {
                query = query.in('status', statuses)
            }
        }

        const { data, error } = await query
        if (error) {
            console.error('[DesktopRenderQueue] list error:', error.message)
            return NextResponse.json({ success: false, error: error.message }, { status: 500 })
        }
        return NextResponse.json({ success: true, rows: data || [] })
    } catch (error: any) {
        console.error('[DesktopRenderQueue] GET error:', error?.message)
        return NextResponse.json({ success: false, error: '서버 오류' }, { status: 500 })
    }
}
