import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { loadStdProjectAssets } from '@/lib/stdProjectAssets'
import { motionForProject, motionScene } from '@/lib/stdMotionStudio'
import { resolveSceneMedia, storageSourceForAsset } from '@/lib/stdSceneMedia'
import { aeSceneSelections, preparedAeScenes } from '@/lib/stdAeScenePreparation'

export const dynamic='force-dynamic'
async function context(req:Request,id:string) {
    const auth=await requireStdUser(req);if(!auth.ok)return {response:auth.response}
    const result=await db.from('std_projects').select('*').eq('id',id).eq('employee_email',auth.requester.email).maybeSingle()
    if(result.error)throw result.error
    if(!result.data)return {response:NextResponse.json({error:'프로젝트를 찾을 수 없습니다.'},{status:404})}
    const assets=await loadStdProjectAssets(db,id,'*');if(assets.error)throw assets.error
    return {project:result.data,assets:assets.data||[]}
}
function summary(assets:any[]) {
    return {preparations:[...aeSceneSelections(assets)].filter(([,a])=>a.metadata.enabled!==false&&a.metadata.result?.plan).map(([number,a])=>({scene_number:number,layers:(a.metadata.result.plan.layers||[]).map((l:any)=>({id:l.id,name:l.name||l.id,role:l.role,depth:l.parallax||0,keys:l.motion||[]}))})),jobs:assets.filter(a=>a.metadata?.kind==='motion_preview').sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at))).slice(0,100).map(a=>({id:a.id,scene_number:a.scene_number,state:a.metadata.state,error:a.metadata.error,suggestion:a.metadata.suggestion||null,
        url:a.metadata.state==='ready'&&a.metadata.gcs_path?`/api/std/assets/gcs-file?bucket=${encodeURIComponent(a.metadata.gcs_bucket)}&path=${encodeURIComponent(a.metadata.gcs_path)}`:null}))}
}
export async function GET(req:Request,{params}:{params:{projectId:string}}) {
    try{const ctx=await context(req,params.projectId);return ctx.response||NextResponse.json(summary(ctx.assets!),{headers:{'Cache-Control':'private, no-store'}})}catch(e:any){return NextResponse.json({error:e.message},{status:400})}
}
export async function POST(req:Request,{params}:{params:{projectId:string}}) {
    try{
        const ctx=await context(req,params.projectId);if(ctx.response)return ctx.response
        const body=await req.json()
        const planning=body.action==='direction'
        if(['approved','canceled'].includes(ctx.project.status)||planning&&ctx.project.submitted_at||!planning&&!ctx.project.submitted_at)return NextResponse.json({error:'연출 준비는 제출 전 대본워커, 실제 미리보기·AE 실행은 제출 후 통합워커에서 담당합니다.'},{status:409})
        const draft=motionForProject(ctx.project);if(!draft?.enabled)throw new Error('Motion Studio 사용 설정을 저장해 주세요.')
        const number=Number(body.scene_number)
        if(!Number.isInteger(number)||number<1)throw new Error('씬 번호를 확인해 주세요.')
        const query=await db.from('std_project_scenes').select('*').eq('project_id',params.projectId).eq('scene_number',number).maybeSingle()
        if(query.error)throw query.error;if(!query.data)throw new Error('프로젝트에 없는 씬입니다.')
        const scene=draft.scenes[String(number)]||motionScene()
        let prepared:any=null
        if(scene.source==='psd') {
            if(body.action==='direction')throw new Error('PSD 감독 계획은 PSD 장면 연출 준비에서 요청해 주세요.')
            const all=await db.from('std_project_scenes').select('*').eq('project_id',params.projectId).order('scene_number')
            if(all.error)throw all.error
            prepared=preparedAeScenes(ctx.project,all.data||[],ctx.assets!).get(number)
            if(!prepared)throw new Error('PSD 레이어 준비·검수를 먼저 완료해 주세요.')
        }
        const asset=prepared ? prepared.metadata.input.source_psd : resolveSceneMedia(ctx.project,query.data,ctx.assets!)
        if(!asset||!storageSourceForAsset(asset))throw new Error('씬에 이미지나 영상을 업로드해 주세요.')
        if (body.action!==undefined&&!['preview','direction'].includes(body.action))throw new Error('지원하지 않는 Motion 작업입니다.')
        const input={version:1,task:body.action==='direction'?'direction':'preview',aspect:draft.aspect,fps:draft.fps,scene,asset,...(prepared?{prepared}:{}),duration:Math.min(10,Math.max(1,Number(query.data.duration_seconds)||5))}
        const fingerprint=createHash('sha256').update(JSON.stringify(input)).digest('hex')
        const existing=ctx.assets!.find(a=>a.metadata?.kind==='motion_preview'&&a.metadata.fingerprint===fingerprint&&['queued','processing','ready'].includes(a.metadata.state))
        if(existing)return NextResponse.json(summary(ctx.assets!))
        if(ctx.assets!.filter(a=>a.metadata?.kind==='motion_preview'&&['queued','processing'].includes(a.metadata.state)).length>=3)throw new Error('미리보기 작업이 3건 진행 중입니다. 완료 후 다시 요청해 주세요.')
        const prior=ctx.assets!.filter(a=>a.metadata?.kind==='motion_preview'&&a.metadata.fingerprint===fingerprint).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)))[0]
        const key=createHash('sha256').update(JSON.stringify({project:params.projectId,fingerprint,previous:prior?.id||null})).digest('hex')
        const id=`${key.slice(0,8)}-${key.slice(8,12)}-5${key.slice(13,16)}-a${key.slice(17,20)}-${key.slice(20,32)}`
        const result=await db.from('std_project_assets').insert({id,project_id:params.projectId,scene_number:number,asset_type:'other',status:'uploaded',mime_type:'application/json',file_name:`motion-preview-${number}.json`,metadata:{kind:'motion_preview',state:'queued',enabled:true,fingerprint,input}}).select('*').single()
        if(result.error){
            if(result.error.code!=='23505')throw result.error
            const recovered=await context(req,params.projectId)
            return recovered.response||NextResponse.json(summary(recovered.assets!))
        }
        return NextResponse.json(summary([...ctx.assets!,result.data]))
    }catch(e:any){return NextResponse.json({error:e.message},{status:400})}
}
