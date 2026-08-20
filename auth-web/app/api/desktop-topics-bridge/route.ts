import { NextResponse } from 'next/server'
import { verifyDesktopSessionToken } from '@/lib/desktopSession'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { isPreparedUserTopic } from '@/lib/preparedTopic'

export const dynamic = 'force-dynamic'

// [AIR-0227E-P4] Narrow, whitelisted bridge for app/routers/user_topics.py.
//
// Why this exists: AIR-0225B (commit 83951d8f) stopped bundling
// SUPABASE_SERVICE_ROLE_KEY into packaged desktop releases (it was leaking
// into public GitHub release zips) but user_topics.py was never migrated off
// direct service_role usage - every packaged desktop build's topic page has
// been silently 500ing since. The fix is NOT to re-embed service_role in the
// desktop app (that undoes the AIR-0225B fix); it's to give the desktop app
// the exact same kind of scoped, session-token-gated proxy that
// /api/desktop-resync already uses for login/profile data.
//
// This is deliberately an ACTION WHITELIST, not a generic "run any Supabase
// query" passthrough - a leaked/stolen session_token can only do exactly the
// 8 things below, each with server-enforced scoping (the caller can never
// substitute another user's email, another table, or another field set).
// No RPC/lease/heartbeat machinery is introduced - this is read/write on
// existing tables only, mirroring the plain PostgREST calls user_topics.py
// used to make directly.

const LONGFORM_POLICY_KEYS = [
    'sys_api_longform_min_duration_minutes',
    'sys_api_longform_base_payout',
    'sys_api_longform_extra_minute_payout',
    'sys_api_longform_duration_lock_enabled',
]

const TRANSLATABLE_LANGS = new Set(['en', 'vi', 'th'])

function unauthorized(detail: string) {
    return NextResponse.json({ status: 'error', detail }, { status: 401 })
}

function badRequest(detail: string) {
    return NextResponse.json({ status: 'error', detail }, { status: 400 })
}

async function verifyApprovedDesktopSession(email: string, sessionToken: string): Promise<boolean> {
    if (!verifyDesktopSessionToken(email, sessionToken)) return false

    const { data, error } = await supabaseAdmin
        .from('profiles')
        .select('is_approved')
        .eq('email', email)
        .maybeSingle()

    if (error || !data) return false
    return data.is_approved === true
}

export async function POST(req: Request) {
    let body: any
    try {
        body = await req.json()
    } catch {
        return badRequest('invalid_json')
    }

    const { email, session_token, action, params } = body || {}
    if (!email || !session_token) {
        return unauthorized('missing_email_or_session_token')
    }
    if (!(await verifyApprovedDesktopSession(String(email), String(session_token)))) {
        return unauthorized('invalid_or_expired_session')
    }
    // From here on, `email` is the server-verified identity - every action
    // below scopes any per-user read/write to THIS email only, regardless of
    // what params.email (if any) claims.
    const verifiedEmail = String(email)
    const p = params || {}

    try {
        switch (action) {
            case 'get_longform_policy': {
                const { data, error } = await supabaseAdmin
                    .from('global_settings')
                    .select('key,value')
                    .in('key', LONGFORM_POLICY_KEYS)
                if (error) throw error
                return NextResponse.json({ status: 'ok', rows: data || [] })
            }

            case 'get_pending_topics': {
                const limit = Math.min(Math.max(Number(p.limit) || 100, 1), 200)
                const { data, error } = await supabaseAdmin
                    .from('topics_queue')
                    .select('*, categories!inner(*)')
                    .eq('status', 'pending')
                    .not('generated_title', 'is', null)
                    .order('created_at', { ascending: false })
                    .limit(limit)
                if (error) throw error
                return NextResponse.json({ status: 'ok', rows: (data || []).filter(isPreparedUserTopic) })
            }

            case 'get_cached_recommendations': {
                const limit = Math.min(Math.max(Number(p.limit) || 20, 1), 100)
                const nowIso = new Date().toISOString()
                const { data, error } = await supabaseAdmin
                    .from('user_topic_recommendations')
                    .select('*')
                    .eq('employee_email', verifiedEmail)
                    .eq('is_claimed', false)
                    .gte('expires_at', nowIso)
                    .order('created_at', { ascending: false })
                    .limit(limit)
                if (error) throw error

                const rows = data || []
                const topicIds = Array.from(new Set(
                    rows
                        .map((row: any) => row.topic_queue_id)
                        .filter((id: any) => id !== null && id !== undefined)
                        .map((id: any) => Number(id))
                        .filter((id: number) => Number.isFinite(id))
                ))

                if (topicIds.length === 0) {
                    if (rows.length > 0) {
                        await supabaseAdmin
                            .from('user_topic_recommendations')
                            .delete()
                            .eq('employee_email', verifiedEmail)
                            .eq('is_claimed', false)
                            .in('id', rows.map((row: any) => row.id))
                    }
                    return NextResponse.json({ status: 'ok', rows: [] })
                }

                const { data: liveTopics, error: liveError } = await supabaseAdmin
                    .from('topics_queue')
                    // Cache rows are only ranking snapshots. Always return the current
                    // queue row so an admin edit or delete is reflected immediately.
                    .select('*, categories!inner(*)')
                    .in('id', topicIds)
                    .eq('status', 'pending')
                    .not('generated_title', 'is', null)
                if (liveError) throw liveError

                const liveTopicById = new Map(
                    (liveTopics || []).filter(isPreparedUserTopic).map((topic: any) => [String(topic.id), topic])
                )
                const pendingTopicIds = new Set(liveTopicById.keys())
                const liveRows = rows
                    .map((row: any) => liveTopicById.get(String(row.topic_queue_id)))
                    .filter(Boolean)
                const staleIds = rows
                    .filter((row: any) => !pendingTopicIds.has(String(row.topic_queue_id)))
                    .map((row: any) => row.id)

                if (staleIds.length > 0) {
                    await supabaseAdmin
                        .from('user_topic_recommendations')
                        .delete()
                        .eq('employee_email', verifiedEmail)
                        .eq('is_claimed', false)
                        .in('id', staleIds)
                }

                return NextResponse.json({ status: 'ok', rows: liveRows })
            }

            case 'save_recommendations': {
                const rows = Array.isArray(p.rows) ? p.rows : []
                await supabaseAdmin
                    .from('user_topic_recommendations')
                    .delete()
                    .eq('employee_email', verifiedEmail)
                    .eq('is_claimed', false)

                if (rows.length === 0) return NextResponse.json({ status: 'ok', inserted: 0 })
                // Force employee_email server-side on every row - a caller can
                // never insert a recommendation cache entry under someone
                // else's identity even if it crafted a different value here.
                const safeRows = rows.map((row: any) => ({ ...row, employee_email: verifiedEmail }))
                const { error } = await supabaseAdmin.from('user_topic_recommendations').insert(safeRows)
                if (error) throw error
                return NextResponse.json({ status: 'ok', inserted: safeRows.length })
            }

            case 'get_profile_prefs': {
                const { data, error } = await supabaseAdmin
                    .from('profiles')
                    .select('preferred_languages, preferred_video_length, preferred_category_ids')
                    .eq('email', verifiedEmail)
                    .maybeSingle()
                if (error) throw error
                return NextResponse.json({ status: 'ok', profile: data || null })
            }

            case 'get_rebalancing_settings': {
                const { data, error } = await supabaseAdmin
                    .from('payout_rebalancing_settings')
                    .select('*')
                    .limit(1)
                if (error) throw error
                return NextResponse.json({ status: 'ok', rows: data || [] })
            }

            case 'get_boosts': {
                const { data, error } = await supabaseAdmin.from('category_priority_boosts').select('*')
                if (error) throw error
                return NextResponse.json({ status: 'ok', rows: data || [] })
            }

            case 'get_stored_translations': {
                const lang = String(p.lang || '')
                const ids = Array.isArray(p.topic_ids) ? p.topic_ids.map((x: any) => String(x)) : []
                if (!TRANSLATABLE_LANGS.has(lang) || ids.length === 0) {
                    return NextResponse.json({ status: 'ok', rows: [] })
                }
                const { data, error } = await supabaseAdmin
                    .from('topics_queue')
                    .select(`id, topic_${lang}, category_name_${lang}`)
                    .in('id', ids)
                if (error) throw error
                return NextResponse.json({ status: 'ok', rows: data || [] })
            }

            case 'save_translations': {
                const lang = String(p.lang || '')
                const topicId = p.topic_id
                if (!TRANSLATABLE_LANGS.has(lang) || !topicId) {
                    return badRequest('invalid_lang_or_topic_id')
                }
                // Field-name whitelist: only these two columns for the given
                // lang can ever be written through this action, regardless of
                // what extra keys params.fields might contain.
                const fields = p.fields || {}
                const patch: Record<string, string> = {
                    [`topic_${lang}`]: String(fields[`topic_${lang}`] || '').trim(),
                    [`category_name_${lang}`]: String(fields[`category_name_${lang}`] || '').trim(),
                }
                const { error } = await supabaseAdmin.from('topics_queue').update(patch).eq('id', topicId)
                if (error) throw error
                return NextResponse.json({ status: 'ok' })
            }

            case 'claim_topic': {
                // Composite action mirroring the exact sequence
                // app/routers/user_topics.py::claim_topic() used to run
                // directly against Supabase - resolve -> fetch -> patch x2.
                // Everything downstream (local project creation, payout
                // normalization) stays in Python; this only does the
                // Supabase-side state change and returns the raw topic row.
                const rawTopicId = String(p.topic_id || '').trim()
                if (!rawTopicId) return badRequest('missing_topic_id')

                let resolvedTopicId: number | null = null
                const { data: recRow } = await supabaseAdmin
                    .from('user_topic_recommendations')
                    .select('topic_queue_id')
                    .eq('id', rawTopicId)
                    .eq('employee_email', verifiedEmail)
                    .limit(1)
                    .maybeSingle()
                if (recRow?.topic_queue_id != null) {
                    resolvedTopicId = Number(recRow.topic_queue_id)
                } else {
                    const asInt = Number(rawTopicId)
                    resolvedTopicId = Number.isFinite(asInt) ? asInt : null
                }
                if (resolvedTopicId == null) {
                    return NextResponse.json({ status: 'error', detail: 'topic_not_found' }, { status: 404 })
                }

                const { data: topicRows, error: topicErr } = await supabaseAdmin
                    .from('topics_queue')
                    .select('*, categories!inner(*)')
                    .eq('id', resolvedTopicId)
                    .limit(1)
                if (topicErr) throw topicErr
                const topicData = (topicRows || [])[0]
                if (!topicData) {
                    return NextResponse.json({ status: 'error', detail: 'topic_not_found' }, { status: 404 })
                }
                // Only claimable if still pending - prevents a race where two
                // claim_topic calls resolve the same topic and both patch it.
                if (topicData.status && topicData.status !== 'pending') {
                    return NextResponse.json({ status: 'error', detail: 'topic_already_claimed' }, { status: 409 })
                }
                if (!isPreparedUserTopic(topicData)) {
                    return NextResponse.json({ status: 'error', detail: 'topic_not_ready' }, { status: 409 })
                }
                const { error: patchErr, data: patchedRows } = await supabaseAdmin
                    .from('topics_queue')
                    .update({
                        status: 'assigned',
                        assigned_employee_email: verifiedEmail,
                        assigned_at: new Date().toISOString(),
                    })
                    .eq('id', resolvedTopicId)
                    .eq('status', 'pending')
                    .select('id')
                if (patchErr) throw patchErr
                if (!patchedRows || patchedRows.length === 0) {
                    return NextResponse.json({ status: 'error', detail: 'topic_already_claimed' }, { status: 409 })
                }

                // Best-effort - mirrors the original's own try/except around this PATCH.
                await supabaseAdmin
                    .from('user_topic_recommendations')
                    .update({ is_claimed: true, claimed_at: new Date().toISOString() })
                    .eq('topic_queue_id', resolvedTopicId)
                    .eq('employee_email', verifiedEmail)

                return NextResponse.json({ status: 'ok', topic: topicData })
            }

            case 'get_claimed_topic_pregeneration': {
                const topicId = Number(p.topic_id)
                if (!Number.isFinite(topicId)) return badRequest('invalid_topic_id')

                // A desktop client may refresh only a topic assigned to the
                // authenticated employee. This prevents one user from reading
                // another user's prepared script through the bridge.
                const { data: topicData, error } = await supabaseAdmin
                    .from('topics_queue')
                    .select('id, generated_title, progress_payload, benchmark_analysis, pregenerated_structure, pregenerated_structure_status, pregenerated_script, pregenerated_script_status')
                    .eq('id', topicId)
                    .eq('assigned_employee_email', verifiedEmail)
                    .maybeSingle()
                if (error) throw error
                if (!topicData) {
                    return NextResponse.json({ status: 'error', detail: 'topic_not_found' }, { status: 404 })
                }
                return NextResponse.json({ status: 'ok', topic: topicData })
            }

            default:
                return badRequest(`unknown_action: ${action}`)
        }
    } catch (error: any) {
        console.error('[DesktopTopicsBridge] Error:', action, error?.message)
        return NextResponse.json({ status: 'error', detail: 'bridge_error' }, { status: 500 })
    }
}
