import { NextResponse } from 'next/server'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireAdmin, isAuthResponse } from '../_auth'
export const dynamic = 'force-dynamic'
const kinds = ['ae_scene_preparation','ae_speaker_coordinates','region_layer_package','motion_preview','ae_mouth_job','motion_automation','horizontal_webtoon_automation','region_motion_plan','effectcraft_automation','filmcraft_automation']
const activeStates = ['queued','pending','processing','rendering','direction_pending','direction_approved','review_pending','needs_review','artifact_ready','ready']
const fields = 'id,project_id,scene_number,created_at,updated_at,kind:metadata->kind,state:metadata->state,phase:metadata->phase,error:metadata->error,progress:metadata->progress,results:metadata->results,total_scenes:metadata->total_scenes,task:metadata->input->task,preview_sync:metadata->preview_sync'
async function allActive(makeQuery: () => any) {
    const rows: any[] = []
    for (let offset = 0; ; offset += 500) {
        const result = await makeQuery().range(offset, offset + 499)
        if (result.error) throw result.error
        rows.push(...(result.data || []))
        if ((result.data || []).length < 500) return rows
    }
}
export async function GET(req: Request) {
    const auth = await requireAdmin(req)
    if (isAuthResponse(auth)) return auth
    try {
        const rawPage = Number(new URL(req.url).searchParams.get('page') || 0)
        const page = Number.isSafeInteger(rawPage) && rawPage >= 0 ? Math.min(rawPage, 10000) : 0
        const assets = () => db.from('std_project_assets').select(fields).in('metadata->>kind', kinds).in('status', ['uploaded','assigned']).order('created_at', {ascending:false}).order('id', {ascending:false})
        const renders = () => db.from('remote_render_queue').select('id,project_name,status,progress,created_at,updated_at,web_project_id:metadata->std_web_project_id,error_message').not('metadata->>std_web_project_id','is',null).order('created_at', {ascending:false}).order('id', {ascending:false})
        const [recent, active, renderRecent, renderActive] = await Promise.all([
            assets().range(page * 100, page * 100 + 99),
            allActive(() => assets().in('metadata->>state',activeStates)),
            renders().range(page * 100, page * 100 + 99),
            allActive(() => renders().in('status',['pending','rendering']))
        ])
        if (recent.error || renderRecent.error) throw recent.error || renderRecent.error
        const rows: any[] = Array.from(new Map([...active,...(recent.data || [])].map((r:any) => [r.id,r])).values())
        const renderRows: any[] = Array.from(new Map([...renderActive,...(renderRecent.data || [])].map((r:any) => [r.id,r])).values())
        const ids = [...new Set([...rows.map(r => r.project_id), ...renderRows.map(r => r.web_project_id)].filter(Boolean))]
        const projects = new Map<string,any>()
        for (let offset=0; offset<ids.length; offset+=200) {
            const result = await db.from('std_projects').select('id,title,topic_queue_id').in('id',ids.slice(offset,offset+200))
            if (result.error) throw result.error
            for (const p of result.data || []) projects.set(p.id,p)
        }
        const jobs = rows.filter(r => !r.preview_sync).map(row => {
            const results = Array.isArray(row.results) ? row.results : []
            const project = projects.get(row.project_id)
            const preparation = ['ae_scene_preparation','ae_speaker_coordinates','region_layer_package'].includes(row.kind) || (row.kind === 'motion_preview' && row.task === 'direction')
            const target = Number(row.total_scenes) || (row.scene_number ? 1 : results.filter((r:any) => r.status !== 'skipped').length)
            return {id:row.id,projectId:row.project_id,title:project?.title || row.project_id,topicId:project?.topic_queue_id,
                kind:row.kind,stage:preparation?'preparation':'production',engine:row.kind?.startsWith('effectcraft')?'EffectCraft':row.kind?.startsWith('filmcraft')?'FilmCraft':'After Effects',
                createdAt:row.created_at,updatedAt:row.updated_at,state:row.state,phase:row.phase || '',error:row.error || '',progress:row.progress || '',
                total:target,analyzed:results.length,target,completed:results.filter((r:any) => ['review_pending','approved','reviewed','ready','completed'].includes(r.status) || r.review?.passed === true || r.review?.skipped === true).length,
                results:results.map((r:any) => ({number:r.number,status:r.status || (r.review?.passed?'reviewed':r.review?.skipped?'not_reviewed':''),speakers:r.speakers || [],note:r.reason || r.direction || '',videoUrl:r.asset_id?`/api/std/projects/${row.project_id}/assets/file?assetId=${r.asset_id}`:''}))}
        })
        for (const row of renderRows) {
            const p = projects.get(row.web_project_id)
            jobs.push({id:row.id,projectId:row.web_project_id,title:p?.title || row.project_name || row.web_project_id,topicId:p?.topic_queue_id,kind:'final_render',stage:'assembly',engine:'최종 조립',createdAt:row.created_at,updatedAt:row.updated_at,state:row.status,phase:'final_render',error:row.error_message || '',progress:Math.max(0,Math.min(100,Number(row.progress)||0)),total:100,analyzed:0,target:100,completed:row.status==='completed'?100:Math.max(0,Math.min(100,Number(row.progress)||0)),results:[]})
        }
        jobs.sort((a,b) => String(b.createdAt).localeCompare(String(a.createdAt)))
        return NextResponse.json({jobs,generatedAt:new Date().toISOString(),historyLimit:100,page,hasMore:(recent.data || []).length===100 || (renderRecent.data || []).length===100}, {headers:{'Cache-Control':'no-store'}})
    } catch {
        return NextResponse.json({error:'제작 작업 현황 조회 실패'}, {status:503})
    }
}
