import { cinematicPlan, cinematicReviewMatches } from './stdWuxiaCinematic'
/** Freeze the same authored state/lettering schedule the editor displays. */
import { correctedWuxiaPackage, isWuxiaMovingtoon, wuxiaSceneFrame } from './stdWuxiaPresentation'
import { wuxiaBubbleContour } from './stdWuxiaBubble'
import { wuxiaGraphicPose, wuxiaTextLines } from './stdWuxiaGraphic'
import { ambientLoopsForState, validAmbientLoop } from './stdAmbientLoop'
import { mouthMatchesRecording, hasWuxiaMouths } from './stdWuxiaMouth'
export function wuxiaStateSource(project:any,number:number) {
 const scene=project.project_payload?.structure?.wuxia_ae_package?.scenes?.find((s:any)=>Number(String(s.scene_id).match(/S(\d+)$/)?.[1])===number)
 const state=scene?.states?.[0]
 if(!state?.sha256)return null
 const url=new URL(state.media_url||state.image_url||'','https://studio.airing.work')
 const path=state.gcs_path||url.searchParams.get('path'),bucket=state.gcs_bucket||url.searchParams.get('bucket')
 if(!path||!bucket)return null
 return {id:`wuxia-${state.asset_id}-${state.sha256}`,asset_type:'image',scene_number:number,status:'assigned',file_name:`${state.asset_id}.png`,metadata:{gcs_bucket:bucket,gcs_path:path,sha256:state.sha256,source_state_asset_id:state.asset_id}}
}
export function freezeWuxiaScene(project:any,number:number,rows:any[],start:number,end:number,fps:number,source:any) {
 if(!isWuxiaMovingtoon(project))return null
 // Final recording times override provisional editor row fields.
 const timedRows=rows.map(r=>({...r,start_num:r.start??r.start_num??r.start_time,end_num:r.end??r.end_num??r.end_time}))
 const first=wuxiaSceneFrame(project,number,timedRows,start)
 if(!first)throw Error(`${number}번 씬의 무협 상태 원화 연출을 확인해 주세요.`)
 const p=project.project_payload||project,pkg=correctedWuxiaPackage(p.structure?.wuxia_ae_package||p.wuxia_ae_package)
 const scene=pkg.scenes.find((s:any)=>Number(String(s.scene_id).match(/S(\d+)$/)?.[1])===number)
 const energyAuto=p.structure?.wuxia_mouth_policy?.energy_auto
 if(energyAuto?.enabled===true&&energyAuto?.auto_prepare===true&&scene.states?.some((s:any)=>s.energy_preparation?.source_sha256!==s.sha256))throw Error(`${number}번 씬 기운 검토를 준비 중입니다. 원화 준비 워커 결과를 기다려 주세요.`)
 if(scene.states?.some((s:any)=>s.energy_preparation?.decision==='present'&&!s.ambient_loops?.some((l:any)=>l.automation==='wuxia_energy_auto/v1'&&validAmbientLoop(l))))throw Error(`${number}번 씬 기운 패치 준비 결과를 확인해 주세요.`)
 const energyRequired=scene.states?.some((s:any)=>s.energy_preparation?.decision==='uncertain'||s.ambient_loops?.some((l:any)=>l.automation==='wuxia_energy_auto/v1'))
 const cinematic=cinematicPlan(project,number),hasCinematic=Boolean(cinematic&&['vignette','panel','slide_blur'].some(k=>cinematic[k]))
 if(hasCinematic&&scene.states.some((s:any)=>!cinematicReviewMatches(s,cinematic,scene.graphics||[])))throw Error(`${number}번 씬의 실제 원화 연출 검토를 기다려 주세요.`)
 const autoPolicy=p.structure?.wuxia_motion_policy?.enabled===true?p.structure.wuxia_motion_policy:energyRequired||hasCinematic?{contract:'wuxia_motion_auto/v1',enabled:true,actual_source_review_required:true,actual_output_review_required:true}:null
 const authored=(p.structure?.scenes||p.scenes||[]).find((s:any)=>Number(s.scene_number||s.scene_order)===number)
 const hasMotion=first.motion.active||Boolean(autoPolicy)||hasCinematic,hasHeat=first.motion.heat.length>0||scene.states?.some((s:any)=>s.heat_shimmer_enabled===true)
 const states=(scene.states||[]).map((s:any)=>{
  const url=new URL(s.media_url||s.image_url||'', 'https://studio.airing.work')
  const path=url.searchParams.get('path'),bucket=url.searchParams.get('bucket')
  const storage=path&&bucket?{gcs_bucket:bucket,gcs_path:path}:s.sha256===source.metadata?.sha256?{gcs_bucket:source.metadata?.gcs_bucket,gcs_path:source.metadata?.gcs_path}:null
  if(!storage?.gcs_path||!storage.gcs_bucket||!/^[a-f0-9]{64}$/.test(s.sha256||''))throw Error(`${number}번 씬 상태 원화의 저장 위치·SHA를 확인해 주세요.`)
  if(!Array.isArray(s.ambient_loops||[])||(s.ambient_loops||[]).length>4||(s.ambient_loops||[]).some((l:any)=>!validAmbientLoop(l)||l.source_sha256!==s.sha256))throw Error(`${number}번 씬 상태의 보조 움직임 원화 연결을 확인해 주세요.`)
  const mouths=(s.energy_only_motion===true?[]:(s.dialogue_mouths||[])).filter((m:any)=>m.enabled)
  if(mouths.length>4||mouths.some((m:any)=>m.source_sha256!==s.sha256||!mouthMatchesRecording(m,project,timedRows)))throw Error(`${number}번 씬 입모양의 원화·음성·대사 시점 연결이 달라졌습니다.`)
  return {asset_id:s.asset_id,sha256:s.sha256,energy_only_motion:s.energy_only_motion===true,...(s.energy_preparation?{energy_preparation:{source_sha256:s.energy_preparation.source_sha256,decision:s.energy_preparation.decision,reason:s.energy_preparation.reason,quality_notes:s.energy_preparation.quality_notes}}:{}),...(s.cinematic_review?{cinematic_review:s.cinematic_review}:{}),...storage,ambient_loops:ambientLoopsForState(s).filter(l=>l.enabled),dialogue_mouths:mouths,
   ...(hasHeat?{heat_face_reviewed:Array.isArray(s.face_exclusion_boxes),heat_protection_boxes:[s.face_exclusion_boxes,s.hand_exclusion_boxes,s.protected_regions].flatMap(b=>Array.isArray(b)?b:[])}:{})}
 })
 const cinematicStates:Record<string,any>={}
 const samples:any[]=[],graphics:Record<string,any>={}
 const hasTransition=first.transition.kind!=='none'
 let transitionSource:any=null
 if(hasTransition&&first.transition.source&&['wipe_left','wipe_right','wipe_up','wipe_down','dissolve'].includes(first.transition.kind)){
  const s=first.transition.source,url=new URL(s.media_url||s.image_url||'','https://studio.airing.work')
  const gcs_path=s.gcs_path||url.searchParams.get('path'),gcs_bucket=s.gcs_bucket||url.searchParams.get('bucket')
  if(!gcs_path||!gcs_bucket||!/^[a-f0-9]{64}$/.test(s.sha256||''))throw Error(`${number}번 씬 전환 배경의 저장 위치·SHA를 확인해 주세요.`)
  transitionSource={asset_id:s.asset_id,sha256:s.sha256,gcs_path,gcs_bucket}
 }
 for(let i=0;i<Math.ceil((end-start)*fps);i++){
  const local=i/fps,frame=wuxiaSceneFrame(project,number,timedRows,start+local,fps)!
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
  if(frame.effects.issues.length)throw Error(`${number}번 씬 충격 연출 검증 실패: ${frame.effects.issues.join(', ')}`)
  if(frame.transition.issues.length)throw Error(`${number}번 씬 전환 검증 실패: ${frame.transition.issues.join(', ')}`)
  if(frame.motion.issues.length)throw Error(`${number}번 씬 이미지 모션 검증 실패: ${frame.motion.issues.join(', ')}`)
  const {source:_,...transition}=frame.transition
  const {descriptor,...cinematicSample}=frame.cinematic
  if(hasCinematic)cinematicStates[frame.state.asset_id]=descriptor
  samples.push({at:local,...(hasCinematic?{cinematic:cinematicSample}:{}),effects:frame.effects.active.length?frame.effects:{},state:frame.state?.asset_id,graphics:visible,
   ...(hasTransition?{transition}:{}),
   ...(hasMotion?{motion:frame.motion.active?frame.motion:{}}:{}),
   mouths:frame.mouths.map((m:any)=>({mouth:current.dialogue_mouths.indexOf(m.mouth),pose:m.pose})),
   ambient:frame.ambient.map(a=>({loop:current.ambient_loops.indexOf(a.loop),frame:a.index}))})
 }
 return {...(hasCinematic?{cinematic_states:cinematicStates,cinematic_plan:cinematic,cinematic_graphics:scene.graphics||[]}:{}),contract:hasCinematic?'wuxia_native_timeline/v6':hasMotion?'wuxia_native_timeline/v5':hasTransition?'wuxia_native_timeline/v4':scene.effects?.length?'wuxia_native_timeline/v3':hasWuxiaMouths(project)?'wuxia_native_timeline/v2':'wuxia_native_timeline/v1',states,graphics,samples,...(autoPolicy?{auto_motion_policy:autoPolicy,motion_selection:authored?.wuxia_motion_selection||{basis:'preserved_manual_setting',image_effect:authored?.metadata?.image_effect??authored?.image_effect??'none'}}:{}),...(transitionSource?{transition_source:transitionSource}:{})}
}
