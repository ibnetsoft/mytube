import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function countBy(rows: any[], key: string) {
    const map = new Map<string, number>()
    for (const row of rows || []) {
        const value = String(row?.[key] || 'unknown')
        map.set(value, (map.get(value) || 0) + 1)
    }
    return Array.from(map.entries())
        .map(([name, count]) => ({ [key]: name, count }))
        .sort((a: any, b: any) => b.count - a.count || String(a[key]).localeCompare(String(b[key])))
}

function buildProjectRows(events: any[], limit: number) {
    const map = new Map<string, any>()
    for (const event of events || []) {
        const projectId = event.local_project_id || 'unknown'
        const key = String(projectId)
        const existing = map.get(key) || {
            project_id: projectId,
            name: event.project_name || '',
            topic: event.project_topic || '',
            event_count: 0,
            last_event_at: event.local_created_at || event.created_at || '',
        }
        existing.event_count += 1
        const eventTime = event.local_created_at || event.created_at || ''
        if (String(eventTime) > String(existing.last_event_at || '')) existing.last_event_at = eventTime
        map.set(key, existing)
    }
    return Array.from(map.values())
        .sort((a, b) => String(b.last_event_at || '').localeCompare(String(a.last_event_at || '')))
        .slice(0, limit)
}

export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const limit = Math.max(1, Math.min(500, Number.parseInt(searchParams.get('limit') || '100', 10) || 100))
        const supabase = getAdmin()

        const { data: events, error } = await supabase
            .from('project_learning_events')
            .select('*')
            .order('local_created_at', { ascending: false, nullsFirst: false })
            .order('created_at', { ascending: false })
            .limit(Math.max(limit, 2000))

        if (error) throw error

        const { count: snapshotCount, error: snapshotError } = await supabase
            .from('project_learning_snapshots')
            .select('id', { count: 'exact', head: true })

        if (snapshotError) throw snapshotError

        const rows = events || []
        const manualReviews = rows.filter((row: any) => row.event_type === 'manual_review')
        const ratings = manualReviews
            .map((row: any) => Number(row?.payload?.rating))
            .filter((value: number) => Number.isFinite(value))

        return NextResponse.json({
            status: 'ok',
            stats: {
                source: 'supabase',
                total_events: rows.length,
                total_snapshots: snapshotCount || 0,
                event_counts: countBy(rows, 'event_type'),
                stage_counts: countBy(rows, 'stage'),
                projects: buildProjectRows(rows, limit),
                recent_events: rows.slice(0, limit).map((row: any) => ({
                    id: row.id,
                    project_id: row.local_project_id,
                    project_name: row.project_name,
                    stage: row.stage,
                    event_type: row.event_type,
                    source: row.source,
                    payload: row.payload || {},
                    created_at: row.local_created_at || row.created_at,
                })),
                manual_review_count: manualReviews.length,
                upload_completed_count: rows.filter((row: any) => row.event_type === 'upload_completed').length,
                upload_failed_count: rows.filter((row: any) => row.event_type === 'upload_failed').length,
                qa_hold_count: rows.filter((row: any) => row.event_type === 'qa_hold').length,
                average_rating: ratings.length ? Math.round((ratings.reduce((sum: number, value: number) => sum + value, 0) / ratings.length) * 100) / 100 : null,
            },
        })
    } catch (error: any) {
        console.error('Learning stats API error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
