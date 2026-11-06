/** Freeze the same authored state/lettering schedule the editor displays. */
import { correctedWuxiaPackage, isWuxiaMovingtoon, wuxiaSceneFrame } from './stdWuxiaPresentation'
import { wuxiaBubbleContour } from './stdWuxiaBubble'
import { wuxiaGraphicPose, wuxiaTextLines } from './stdWuxiaGraphic'
import { ambientLoopsForState, validAmbientLoop } from './stdAmbientLoop'
export function freezeWuxiaScene(project:any,number:number,rows:any[],start:number,end:number,fps:number,source:any) {
 if(!isWuxiaMovingtoon(project))return null
 // Final recording times override provisional editor row fields.
 const timedRows=rows.map(r=>({...r,start_num:r.start??r.start_num??r.start_time,end_num:r.end??r.end_num??r.end_time}))
 const first=wuxiaSceneFrame(project,number,timedRows,start)
 if(!first)throw Error(`${number}번 씬의 무협 상태 원화 연출을 확인해 주세요.`)
 const p=project.project_payload||project,pkg=correctedWuxiaPackage(p.structure?.wuxia_ae_package||p.wuxia_ae_package)
 const scene=pkg.scenes.find((s:any)=>Number(String(s.scene_id).match(/S(\d+)$/)?.[1])===number)
 const states=(scene.states||[]).map((s:any)=>{
  const url=new URL(s.media_url||s.image_url||'', 'https://studio.airing.work')
  const path=url.searchParams.get('path'),bucket=url.searchParams.get('bucket')
  const storage=path&&bucket?{gcs_bucket:bucket,gcs_path:path}:s.sha256===source.metadata?.sha256?{gcs_bucket:source.metadata?.gcs_bucket,gcs_path:source.metadata?.gcs_path}:null
  if(!storage?.gcs_path||!storage.gcs_bucket||!/^[a-f0-9]{64}$/.test(s.sha256||''))throw Error(`${number}번 씬 상태 원화의 저장 위치·SHA를 확인해 주세요.`)
  if(!Array.isArray(s.ambient_loops||[])||(s.ambient_loops||[]).length>4||(s.ambient_loops||[]).some((l:any)=>!validAmbientLoop(l)||l.source_sha256!==s.sha256))throw Error(`${number}번 씬 상태의 보조 움직임 원화 연결을 확인해 주세요.`)
  return {asset_id:s.asset_id,sha256:s.sha256,...storage,ambient_loops:ambientLoopsForState(s).filter(l=>l.enabled)}
 })
 const samples:any[]=[],graphics:Record<string,any>={}
 for(let i=0;i<Math.ceil((end-start)*fps);i++){
  const local=i/fps,frame=wuxiaSceneFrame(project,number,timedRows,start+local)!
  const visible:any[]=[]
  for(const g of frame.graphics){
   const id=String((scene.graphics||[]).findIndex((item:any)=>item.block_id===g.block_id&&item.state_asset_id===g.state_asset_id&&item.kind===g.kind&&item.text===g.text))
   if(!graphics[id]){
    const l=g.layout,s=g.style||{},speech=g.kind==='speech_bubble',w=l.size[0]*1920,h=l.size[1]*1080
    const lines=wuxiaTextLines(g.text,w*(speech?.72:.94),s.size||38),size=Math.min(s.size||38,h*.76/(lines.length*1.16))
    const points=speech?wuxiaBubbleContour([l.center[0]*1920,l.center[1]*1080],[w,h],l.offscreen_speaker?undefined:l.tail?.map((n:number,a:number)=>n*(a?1080:1920)),g.bubble_style).points:null
    graphics[id]={...g,points,lines,font_size:size}
   }
   visible.push({id,...wuxiaGraphicPose(g,g.progress)})
  }
  const current=states.find((s:any)=>s.asset_id===frame.state?.asset_id)
  samples.push({at:local,state:frame.state?.asset_id,graphics:visible,
   ambient:frame.ambient.map(a=>({loop:current.ambient_loops.indexOf(a.loop),frame:a.index}))})
 }
 return {contract:'wuxia_native_timeline/v1',states,graphics,samples}
}
