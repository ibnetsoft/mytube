import { validAmbientLoop } from './stdAmbientLoop'
const ENERGY='wuxia_energy_auto/v1'
function energyFields(local:any,remote:any){
 if(remote?.energy_preparation?.source_sha256!==local.sha256)return {}
 const raw=(remote.ambient_loops||[]).filter((l:any)=>l.automation===ENERGY)
 if(raw.some((l:any)=>l.source_sha256!==local.sha256||!validAmbientLoop(l))||(remote.energy_preparation.decision==='present'&&!raw.length))return {}
 const loops=[...(local.ambient_loops||[]).filter((l:any)=>l.automation!==ENERGY),...(remote.ambient_loops||[]).filter((l:any)=>l.automation===ENERGY&&l.source_sha256===local.sha256&&validAmbientLoop(l))]
 if(loops.length>4)return {}
 return {ambient_loops:loops,energy_preparation:remote.energy_preparation,energy_only_motion:remote.energy_only_motion===true}
}
/** Overlay worker results onto matching originals only; local edits are authoritative. */
export function mergeWuxiaMouthRefresh(project:any,update:any):any {
 const p=project?.project_payload||project
 if(!update?.success||!p?.structure?.wuxia_ae_package||update.project_id!==project.id
  ||p.structure.wuxia_mouth_policy?.auto_prepare!==true)return project
 const voiceMatches=update.audio_id===p.subtitle_source_audio_id
 if(!voiceMatches&&!update.states?.some((s:any)=>s.energy_preparation))return project
 const pkg=p.structure.wuxia_ae_package
 const next={...p,structure:{...p.structure,wuxia_ae_package:{...pkg,scenes:pkg.scenes.map((sc:any)=>({...sc,states:sc.states.map((st:any)=>{
  const remote=update.states.find((r:any)=>r.scene_id===sc.scene_id&&r.asset_id===st.asset_id&&r.sha256===st.sha256)
  if(!remote)return st
  if(!voiceMatches||JSON.stringify(remote.graphics)!==JSON.stringify(sc.graphics))return {...st,...energyFields(st,remote)}
  return {...st,...energyFields(st,remote),dialogue_mouths:[...(st.dialogue_mouths||[]).filter((m:any)=>m.automation!=='wuxia_mouth_auto/v1'),
   ...remote.dialogue_mouths.filter((m:any)=>m.automation==='wuxia_mouth_auto/v1'&&m.source_sha256===st.sha256)]}
 })}))}}}
 return project.project_payload?{...project,project_payload:next}:next
}

/** A stale editor save must not erase results published by the preparation worker. */
export function preserveWuxiaMouthPreparation(current:any,next:any):any {
 if(current?.wuxia_mouth_policy?.auto_prepare!==true||!current?.wuxia_ae_package||!next?.wuxia_ae_package)return next
 const previous=current.wuxia_ae_package
 let unchanged=true
 const scenes=next.wuxia_ae_package.scenes.map((sc:any)=>{
  const old=previous.scenes.find((p:any)=>p.scene_id===sc.scene_id)
  const sameGraphics=JSON.stringify(old?.graphics)===JSON.stringify(sc.graphics)
  return {...sc,states:sc.states.map((st:any)=>{
   const original=old?.states.find((p:any)=>p.asset_id===st.asset_id&&p.sha256===st.sha256)
   if(!original||!sameGraphics){unchanged=false;return {...st,...(original?energyFields(st,original):{energy_preparation:undefined,energy_only_motion:undefined,ambient_loops:(st.ambient_loops||[]).filter((l:any)=>l.automation!==ENERGY)}),dialogue_mouth_preparation:undefined,dialogue_mouths:(st.dialogue_mouths||[]).filter((m:any)=>m.automation!=='wuxia_mouth_auto/v1')}}
   return {...st,...energyFields(st,original),dialogue_mouth_preparation:original.dialogue_mouth_preparation,
    dialogue_mouths:[...(st.dialogue_mouths||[]).filter((m:any)=>m.automation!=='wuxia_mouth_auto/v1'),
     ...(original.dialogue_mouths||[]).filter((m:any)=>m.automation==='wuxia_mouth_auto/v1')]}
  })}
 })
 return {...next,wuxia_mouth_policy:{...current.wuxia_mouth_policy,...next.wuxia_mouth_policy},wuxia_ae_package:{...next.wuxia_ae_package,scenes,
  mouth_preparation:unchanged?previous.mouth_preparation:undefined,mouth_timing:unchanged?previous.mouth_timing:undefined}}
}
