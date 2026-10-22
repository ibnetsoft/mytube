import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
export const dynamic='force-dynamic'
export async function GET(req:Request,{params}:{params:{projectId:string}}) {
    const auth=await requireStdUser(req);if(!auth.ok)return auth.response
    const project=await db.from('std_projects').select('id').eq('id',params.projectId).eq('employee_email',auth.requester.email).maybeSingle()
    if(project.error)return NextResponse.json({error:'상태를 조회하지 못했습니다.'},{status:503})
    if(!project.data)return NextResponse.json({error:'Project not found'},{status:404})
    const result=await db.from('std_project_assets').select('id,kind:metadata->>kind,state:metadata->>state,phase:metadata->>phase,progress:metadata->progress,error:metadata->>error,results:metadata->results,total_scenes:metadata->total_scenes,supplemental_assets:metadata->supplemental_assets,final:metadata->final').eq('project_id',params.projectId).in('metadata->>kind',['motion_automation','effectcraft_automation']).order('created_at',{ascending:false}).limit(1).maybeSingle()
    if(result.error)return NextResponse.json({error:'작업 상태를 조회하지 못했습니다.'},{status:503})
    const job=result.data,m:any=job||{}
    const engine=m?.kind==='effectcraft_automation'?'effectcraft':m?.kind==='filmcraft_automation'?'filmcraft':'ae'
    return NextResponse.json({job:job?{id:job.id,engine,state:m.state,phase:m.phase,progress:m.progress,error:m.error,
        reviewed_scenes:(m.results||[]).length,total_scenes:m.total_scenes,
        supplemental_scenes:new Set((m.supplemental_assets||[]).filter((a:any)=>a.reviewed===true).map((a:any)=>a.number)).size,
        supplemental_files:(m.supplemental_assets||[]).filter((a:any)=>a.reviewed===true).reduce((sum:number,a:any)=>sum+(Number(a.file_count)||0),0),
        final_url:m.state==='complete'&&m.final?.gcs_path?`/api/std/assets/gcs-file?bucket=${encodeURIComponent(m.final.gcs_bucket)}&path=${encodeURIComponent(m.final.gcs_path)}`:null}:null},{headers:{'Cache-Control':'no-store'}})
}
