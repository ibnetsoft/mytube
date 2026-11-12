import {createHash} from 'crypto'
import {NextResponse} from 'next/server'
import {supabaseAdmin as db} from '@/lib/supabaseAdmin'
import {requireStdUser} from '@/lib/stdWeb'
import {loadStdProjectAssets} from '@/lib/stdProjectAssets'
import {selectNarrationAsset,assertNarrationIdentity} from '@/lib/stdContentIdentity'
import {lipSyncPlan,lipSyncSceneStarts} from '@/lib/stdLipSync'
import {coordinateSource} from '@/lib/stdSpeakerGeometry'
import {downloadGcsObject,createGcsSignedReadUrl} from '@/lib/gcsStorage'

export const dynamic='force-dynamic'
const roles=['mouth_closed','mouth_half','mouth_open','blink','hair'] as const
const sha=(b:Buffer)=>createHash('sha256').update(b).digest('hex')
const hash=(s:any)=>createHash('sha256').update(JSON.stringify(s)).digest('hex')
const validSha=(s:any)=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s)
async function context(req:Request,id:string){
 const auth=await requireStdUser(req);if(!auth.ok)return {response:auth.response}
 const project=await db.from('std_projects').select('*').eq('id',id).eq('employee_email',auth.requester.email).maybeSingle()
 if(project.error)throw project.error
 if(!project.data||['canceled','cancelled'].includes(project.data.status))return {response:NextResponse.json({error:'프로젝트를 찾을 수 없습니다.'},{status:404})}
 const assets=await loadStdProjectAssets(db,id,'*');if(assets.error)throw assets.error
 return {project:project.data,assets:(assets.data||[]).filter((a:any)=>['uploaded','assigned'].includes(a.status)).sort((a:any,b:any)=>String(b.created_at).localeCompare(String(a.created_at)))}
}
export async function GET(req:Request,{params}:{params:{projectId:string}}){
 try{
  const c=await context(req,params.projectId);if(c.response)return c.response
  const q=new URL(req.url).searchParams,scene=Number(q.get('scene')),id=q.get('id')
  if(!Number.isInteger(scene)||scene<1)throw Error('씬 번호를 확인해 주세요.')
  const jobs=c.assets!.filter((a:any)=>a.scene_number===scene&&a.metadata?.kind==='motion2d_render')
  if(id){const job=jobs.find((a:any)=>a.id===id);if(!job)return NextResponse.json({error:'작업을 찾을 수 없습니다.'},{status:404})
   const m=job.metadata,input=m.input;let current=true
   if(m.state==='ready')try{
    const image=c.assets!.find((a:any)=>a.asset_type==='image'&&a.scene_number===scene)
    if(!image||image.id!==input.image.id)throw Error('image changed')
    const ref=coordinateSource(image),bytes=await downloadGcsObject({bucket:ref.bucket,objectPath:ref.path});if(sha(bytes)!==input.image_sha256)throw Error('image changed')
    for(const role of roles){const latest=c.assets!.find((a:any)=>a.scene_number===scene&&a.metadata?.kind==='motion2d_patch'&&a.metadata?.role===role&&a.metadata?.imageId===image.id&&a.metadata?.imageSha256===input.image_sha256);if(!latest||latest.id!==input.patches[role].id||latest.metadata.sha256!==input.patches[role].metadata.sha256)throw Error('patch changed')}
    const bg=c.assets!.find((a:any)=>a.id===input.background.id);if(!bg||bg.metadata?.sha256!==input.background.metadata.sha256||(q.has('backgroundId')&&q.get('backgroundId')!==input.background.id))throw Error('background changed')
    const audio=selectNarrationAsset(c.project,c.assets!);if(audio.id!==input.audio.id||audio.metadata?.sha256!==input.audio_sha256)throw Error('audio changed');assertNarrationIdentity(c.project,audio,c.project.project_payload?.subtitles||[])
    const scenes=await db.from('std_project_scenes').select('id,scene_number').eq('project_id',params.projectId).order('scene_number');if(scenes.error)throw scenes.error;const sceneRows=scenes.data||[];lipSyncPlan(c.project,sceneRows,c.assets!);if(JSON.stringify(sceneRows.map((s:any)=>({id:s.id,scene_number:Number(s.scene_number)})))!==JSON.stringify(input.scene_identity))throw Error('scene order changed');const index=sceneRows.findIndex((s:any)=>Number(s.scene_number)===scene),starts=lipSyncSceneStarts(c.project,sceneRows,audio);if(index<0||Math.abs(Number(starts[index])-input.audio_start)>.001)throw Error('scene timing changed')
   }catch{current=false}
   const state=current?m.state:'stale',result=state==='ready'&&m.result?.gcs_bucket&&m.result?.gcs_path?await createGcsSignedReadUrl({bucket:m.result.gcs_bucket,objectPath:m.result.gcs_path,expiresInMinutes:30}):null
   return NextResponse.json({id:job.id,state,error:m.error||null,url:result,source_image_id:input?.image?.id},{headers:{'Cache-Control':'private, no-store'}})
  }
  return NextResponse.json({jobs:jobs.slice(0,10).map((a:any)=>({id:a.id,state:a.metadata.state,created_at:a.created_at,image_id:a.metadata.input?.image?.id}))},{headers:{'Cache-Control':'private, no-store'}})
 }catch(e:any){return NextResponse.json({error:e.message},{status:400})}
}
export async function POST(req:Request,{params}:{params:{projectId:string}}){
 try{
  const c=await context(req,params.projectId);if(c.response)return c.response
  if(c.project.submitted_at||['approved','review_requested','completed','paid'].includes(c.project.status))throw Error('제출 전 프로젝트에서 2D 미리보기를 만들어 주세요.')
  const body=await req.json(),scene=Number(body.scene),imageSha=String(body.imageSha256||''),backgroundId=String(body.backgroundAssetId||'')
  if(!Number.isInteger(scene)||scene<1||!validSha(imageSha))throw Error('씬과 원본을 확인해 주세요.')
  const image=c.assets!.find((a:any)=>a.asset_type==='image'&&a.scene_number===scene)
  if(!image||image.id!==body.imageId)throw Error('씬 원본이 변경되었습니다.')
  const source=coordinateSource(image),bytes=await downloadGcsObject({bucket:source.bucket,objectPath:source.path})
  if(sha(bytes)!==imageSha)throw Error('원본 이미지가 변경되었습니다.')
  const background=c.assets!.find((a:any)=>a.id===backgroundId&&a.scene_number===scene&&a.metadata?.kind==='region_layer_upload'&&a.metadata?.role==='background'&&a.metadata?.imageId===image.id&&a.metadata?.imageSha256===imageSha)
  if(!background||!validSha(background.metadata.sha256))throw Error('현재 이미지의 복원 배경을 먼저 등록해 주세요.')
  const patches:any={}
  for(const role of roles){const a=c.assets!.find((x:any)=>x.scene_number===scene&&x.metadata?.kind==='motion2d_patch'&&x.metadata?.role===role&&x.metadata?.imageId===image.id&&x.metadata?.imageSha256===imageSha)
   if(!a||!validSha(a.metadata.sha256))throw Error(`${role}: 현재 이미지에 맞는 패치를 먼저 저장해 주세요.`);patches[role]=a}
  const audio=selectNarrationAsset(c.project,c.assets!),subtitles=c.project.project_payload?.subtitles||[]
  assertNarrationIdentity(c.project,audio,subtitles)
  if(!validSha(audio.metadata?.sha256))throw Error('확정 음성의 SHA-256 기록이 필요합니다.')
  const scenes=await db.from('std_project_scenes').select('id,scene_number').eq('project_id',params.projectId).order('scene_number');if(scenes.error)throw scenes.error
  const rows=scenes.data||[],index=rows.findIndex((s:any)=>Number(s.scene_number)===scene)
  if(index<0)throw Error('씬 시간표가 없습니다.')
  lipSyncPlan(c.project,rows,c.assets!)
  const starts=lipSyncSceneStarts(c.project,rows,audio),start=Number(starts[index]),end=Number(starts[index+1]??audio.metadata.subtitle_timeline?.at(-1)?.end)
  if(!Number.isFinite(start)||!Number.isFinite(end)||end-start<4)throw Error('이 씬의 확정 음성 구간이 4초 이상이어야 합니다.')
  const scene_identity=rows.map((s:any)=>({id:s.id,scene_number:Number(s.scene_number)}))
  const input={version:1,project_id:params.projectId,scene,scene_identity,image,image_sha256:imageSha,audio,audio_sha256:audio.metadata.sha256,audio_start:start,patches,background}
  const fingerprint=hash({version:1,scene,scene_identity,image:image.id,imageSha,audio:audio.id,audioSha:audio.metadata.sha256,start,background:[background.id,background.metadata.sha256],patches:roles.map(r=>[r,patches[r].id,patches[r].metadata.sha256])})
  const metadata={kind:'motion2d_render',version:1,state:'queued',fingerprint,input,workflow_stage:'preparation'}
  const id=`${fingerprint.slice(0,8)}-${fingerprint.slice(8,12)}-5${fingerprint.slice(13,16)}-a${fingerprint.slice(17,20)}-${fingerprint.slice(20,32)}`
  const prior=c.assets!.find((a:any)=>a.id===id&&a.metadata?.kind==='motion2d_render'&&a.metadata.fingerprint===fingerprint)
  if(prior&&prior.metadata.state!=='failed')return NextResponse.json({id,state:prior.metadata.state})
  if(prior){const retry=await db.from('std_project_assets').update({metadata,updated_at:new Date().toISOString()}).eq('id',id).eq('updated_at',prior.updated_at).select('id').maybeSingle();if(retry.error)throw retry.error;if(!retry.data)throw Error('작업 상태가 변경되었습니다. 다시 확인해 주세요.');return NextResponse.json({id,state:'queued'})}
  const saved=await db.from('std_project_assets').insert({id,project_id:params.projectId,scene_number:scene,asset_type:'other',status:'uploaded',file_name:`motion2d-render-${scene}.json`,mime_type:'application/json',metadata}).select('id').single()
  if(saved.error&&saved.error.code==='23505')return NextResponse.json({id,state:'queued'})
  if(saved.error)throw saved.error
  return NextResponse.json({id,state:'queued'})
 }catch(e:any){return NextResponse.json({error:e.message},{status:400})}
}
