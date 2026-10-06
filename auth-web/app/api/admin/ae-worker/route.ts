import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireAdmin, isAuthResponse } from '../_auth'
export const dynamic = 'force-dynamic'
export async function GET(req: Request) {
    const auth = await requireAdmin(req)
    if (isAuthResponse(auth)) return auth
    const query = (active: boolean) => {
        let q = supabaseAdmin.from('std_project_assets').select('id,project_id,created_at,updated_at,metadata')
            .eq('metadata->>kind', 'ae_mouth_job').in('status', ['uploaded', 'assigned'])
        if (active) q = q.in('metadata->>state', ['queued', 'processing', 'direction_pending', 'direction_approved', 'review_pending'])
        return q.order('created_at', { ascending: false }).limit(active ? 200 : 100)
    }
    const [recent, active] = await Promise.all([query(false), query(true)])
    if (recent.error || active.error) return NextResponse.json({ error: 'AE 작업 큐 조회 실패' }, { status: 503 })
    const rows = Array.from(new Map([...(active.data || []), ...(recent.data || [])].map(r => [r.id, r])).values())
    const ids = [...new Set(rows.map(r => r.project_id))]
    const projects = ids.length ? await supabaseAdmin.from('std_projects').select('id,title,topic_queue_id').in('id', ids) : { data: [], error: null }
    if (projects.error) return NextResponse.json({ error: '프로젝트 조회 실패' }, { status: 503 })
    const jobs = rows.map(row => {
        const m = row.metadata || {}, results = m.results || []
        const project = projects.data?.find(p => p.id === row.project_id)
        const target = results.filter((r: any) => r.status !== 'skipped').length
        const completed = results.filter((r: any) => ['review_pending', 'approved'].includes(r.status)).length
        return { id: row.id, projectId: row.project_id, title: project?.title || row.project_id, topicId: project?.topic_queue_id,
            createdAt: row.created_at, updatedAt: row.updated_at, state: m.state, phase: m.phase || 'discovery', error: m.error || '',
            total: m.input?.scenes?.length || 0, analyzed: results.length, target, completed,
            results: results.map((r: any) => ({ number: r.number, status: r.status, speakers: r.speakers || [], note: r.reason || r.direction || '',
                videoUrl: r.asset_id ? `/api/std/projects/${row.project_id}/assets/file?assetId=${r.asset_id}` : '' })) }
    })
    return NextResponse.json({ jobs, generatedAt: new Date().toISOString(), historyLimit: 100 }, { headers: { 'Cache-Control': 'no-store' } })
}
