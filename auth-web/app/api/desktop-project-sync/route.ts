import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0225B] services/project_sync_service.py talked to Supabase's
// desktop_project_metadata table directly via SUPABASE_SERVICE_ROLE_KEY -
// harmless-looking, since it's just project text metadata, but that key was
// removed from packaged desktop builds. has_supabase() has silently returned
// False in every build since, so fetch_remote_projects()/
// ensure_local_projects_from_remote() have quietly no-opped on every call:
// a fresh install (or any machine whose local SQLite lost a project row)
// shows an empty project list even though the row is sitting right here in
// Supabase, with no error surfaced anywhere. Same email + HMAC
// session_token bridge pattern as desktop-referrals/desktop-support.

const TABLE = 'desktop_project_metadata'
const MAX_PAYLOAD_BYTES = 2_000_000 // project_payload/progress_payload are JSON blobs of project text - guard against abuse, not normal use

async function resolveUser(email: string): Promise<{ id: string } | null> {
    const { data, error } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data) return null
    return data
}

async function actionList(email: string) {
    // employee_email match (not user_id) to stay compatible with rows written
    // before this migration, some of which may have user_id=null if the
    // old client-side _resolve_user_id() lookup failed at write time.
    const { data, error } = await supabaseAdmin
        .from(TABLE)
        .select('sync_id, name, topic, status, language, app_mode, employee_email, project_payload, deleted_at, created_at, updated_at')
        .eq('employee_email', email)
        .is('deleted_at', null)
        .order('updated_at', { ascending: false })

    if (error) {
        return { success: false, error: '원격 프로젝트 목록 조회에 실패했습니다.' }
    }
    return { success: true, projects: data || [] }
}

async function actionPush(email: string, userId: string, body: any) {
    const syncId = String(body.sync_id || '').trim()
    if (!syncId) {
        return { success: false, error: 'sync_id is required' }
    }

    const payloadSize = JSON.stringify(body.project_payload || {}).length + JSON.stringify(body.progress_payload || {}).length
    if (payloadSize > MAX_PAYLOAD_BYTES) {
        return { success: false, error: 'project payload too large' }
    }

    // Ownership check: a sync_id is a client-generated local id. Refuse to let
    // one account's push overwrite a row that already belongs to someone else.
    const { data: existing } = await supabaseAdmin
        .from(TABLE)
        .select('employee_email')
        .eq('sync_id', syncId)
        .maybeSingle()
    if (existing && existing.employee_email && existing.employee_email !== email) {
        return { success: false, error: 'sync_id belongs to a different account' }
    }

    const now = new Date().toISOString()
    const row = {
        sync_id: syncId,
        user_id: userId,
        employee_email: email,
        local_project_id: body.local_project_id ?? null,
        name: String(body.name || '').slice(0, 500),
        topic: String(body.topic || '').slice(0, 2000),
        status: String(body.status || 'draft').slice(0, 50),
        language: String(body.language || 'ko').slice(0, 10),
        app_mode: String(body.app_mode || 'longform').slice(0, 50),
        project_payload: body.project_payload ?? null,
        progress_payload: body.progress_payload ?? null,
        deleted_at: body.deleted_at ?? null,
        updated_at: now,
        synced_at: now,
    }

    const { error } = await supabaseAdmin
        .from(TABLE)
        .upsert(row, { onConflict: 'sync_id' })

    if (error) {
        return { success: false, error: '동기화에 실패했습니다.' }
    }
    return { success: true }
}

async function actionSoftDelete(email: string, body: any) {
    const syncId = String(body.sync_id || '').trim()
    if (!syncId) {
        return { success: false, error: 'sync_id is required' }
    }

    const { data: existing } = await supabaseAdmin
        .from(TABLE)
        .select('employee_email')
        .eq('sync_id', syncId)
        .maybeSingle()
    if (!existing) {
        // Nothing to delete remotely - the project was local-only. Not an error.
        return { success: true }
    }
    if (existing.employee_email && existing.employee_email !== email) {
        return { success: false, error: 'sync_id belongs to a different account' }
    }

    const now = new Date().toISOString()
    const { error } = await supabaseAdmin
        .from(TABLE)
        .update({
            name: String(body.name || '').slice(0, 500),
            topic: String(body.topic || '').slice(0, 2000),
            status: 'deleted',
            deleted_at: now,
            updated_at: now,
            synced_at: now,
        })
        .eq('sync_id', syncId)

    if (error) {
        return { success: false, error: '원격 삭제 동기화에 실패했습니다.' }
    }
    return { success: true }
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { email, session_token, action } = body

        if (!email || !session_token || !action) {
            return NextResponse.json({ success: false, error: 'Missing email, session_token or action' }, { status: 400 })
        }
        const normalizedEmail = String(email)

        if (!verifyDesktopSessionToken(normalizedEmail, String(session_token))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        switch (String(action)) {
            case 'list':
                return NextResponse.json(await actionList(normalizedEmail))
            case 'push': {
                const user = await resolveUser(normalizedEmail)
                if (!user) {
                    return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
                }
                return NextResponse.json(await actionPush(normalizedEmail, user.id, body))
            }
            case 'soft_delete':
                return NextResponse.json(await actionSoftDelete(normalizedEmail, body))
            default:
                return NextResponse.json({ success: false, error: `Unknown action: ${action}` }, { status: 400 })
        }
    } catch (error: any) {
        console.error('[DesktopProjectSync] Error:', error?.message)
        return NextResponse.json({ success: false, error: '프로젝트 동기화 서버 오류' }, { status: 500 })
    }
}
