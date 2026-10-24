import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { webtoonInputs } from '@/lib/stdHorizontalWebtoon'
export const dynamic='force-dynamic'
export const maxDuration=120
async function context(req:Request,id:string) {
    const auth=await requireStdUser(req)
    if(!auth.ok)return {response:auth.response}
    const p=await db.from('std_projects').select('*').eq('id',id).eq('employee_email',auth.requester.email).maybeSingle()
    if(p.error)throw p.error
    if(!p.data)return {response:NextResponse.json({error:'프로젝트를 찾을 수 없습니다.'},{status:404})}
    const s=await db.from('std_project_scenes').select('*').eq('project_id',id).order('scene_number')
    if(s.error)throw s.error
    const assets:any[]=[]
    for(let start=0;;start+=500){const a=await db.from('std_project_assets').select('*').eq('project_id',id).in('status',['uploaded','assigned']).order('id').range(start,start+499);if(a.error)throw a.error;assets.push(...(a.data||[]));if((a.data||[]).length<500)break}
    return {project:p.data,assets,scenes:s.data||[]}
}
async function handle(req:Request,id:string,enqueue:boolean) {
    try{
        const ctx=await context(req,id);if(ctx.response)return ctx.response
        if(enqueue&&(ctx.project.submitted_at||['approved','canceled'].includes(ctx.project.status)))return NextResponse.json({error:'제출 전 대본워커에서 연출을 준비해 주세요.'},{status:409})
        const items=webtoonInputs(ctx.project,ctx.scenes,ctx.assets)
        if(!items.length)throw Error('원본 씬을 먼저 등록해 주세요.')
        const result=[]
        for(const item of items){
            let job=ctx.assets.filter(a=>a.metadata?.kind==='motion_preview'&&a.metadata.fingerprint===item.fingerprint).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)))[0]
            if(enqueue&&(!job||!['queued','processing','ready'].includes(job.metadata.state))){
                const key=createHash('sha256').update(JSON.stringify({project:id,fingerprint:item.fingerprint,prior:job?.id||null})).digest('hex')
                const jobId=`${key.slice(0,8)}-${key.slice(8,12)}-5${key.slice(13,16)}-a${key.slice(17,20)}-${key.slice(20,32)}`
                const insert=await db.from('std_project_assets').insert({id:jobId,project_id:id,scene_number:item.number,asset_type:'other',status:'uploaded',mime_type:'application/json',file_name:`horizontal-webtoon-${item.number}.json`,metadata:{kind:'motion_preview',state:'queued',enabled:true,fingerprint:item.fingerprint,input:item.input}}).select('*').single()
                if(insert.error&&insert.error.code!=='23505')throw insert.error
                if(insert.error){const existing=await db.from('std_project_assets').select('*').eq('id',jobId).single();if(existing.error)throw existing.error;job=existing.data}else job=insert.data
            }
            result.push({number:item.number,state:job?.metadata?.state||'not_prepared',error:job?.metadata?.error||null,shots:job?.metadata?.suggestion?.webtoon?.shots?.length||0,motion_capability:job?.metadata?.suggestion?.webtoon?.motion_capability||(item.asset.asset_type==='video'?'existing_video':'pending')})
        }
        return NextResponse.json({scenes:result,ready:result.filter(s=>s.state==='ready').length,total:result.length},{headers:{'Cache-Control':'private, no-store'}})
    }catch(e:any){return NextResponse.json({error:e.message},{status:400})}
}
export const GET=(req:Request,{params}:{params:{projectId:string}})=>handle(req,params.projectId,false)
export const POST=(req:Request,{params}:{params:{projectId:string}})=>handle(req,params.projectId,true)
