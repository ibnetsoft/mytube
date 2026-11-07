/** Optional mouth patches belong to one reviewed state, speaker and saved recording. */
export const WUXIA_MOUTH_CONTRACT='wuxia_dialogue_mouth/v1'
export const stateMouths=(state:any):any[]=>Array.isArray(state?.dialogue_mouths)?state.dialogue_mouths:[]
const sha=(v:any)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v)
const num=(v:any)=>typeof v==='number'&&Number.isFinite(v)
const rect=(r:any)=>Array.isArray(r)&&r.length===4&&r.every((v:any)=>num(v)&&v>=0&&v<=1)&&r[0]<r[2]&&r[1]<r[3]
export function validWuxiaMouth(m:any):boolean {
 if(!m||m.contract!==WUXIA_MOUTH_CONTRACT||typeof m.enabled!=='boolean'||!sha(m.source_sha256)||!sha(m.audio_sha256)||typeof m.audio_asset_id!=='string'
  ||!rect(m.face_box)||!rect(m.mouth_box)||m.face_box[3]-m.face_box[1]<.20||m.mouth_box[2]-m.mouth_box[0]<.014
  ||m.mouth_box.some((v:number,i:number)=>i<2?v<m.face_box[i]:v>m.face_box[i])
  ||!Number.isInteger(m.width)||!Number.isInteger(m.height)||m.width<1||m.height<1||m.width*m.height>16000000
  ||m.review?.mouth_fully_visible!==true||m.review?.face_large_enough!==true||m.review?.occluded!==false||m.review?.identity_preserved!==true
  ||!Array.isArray(m.block_ids)||!m.block_ids.length||!m.block_ids.every((s:any)=>typeof s==='string')
  ||typeof m.speaker!=='string'||!m.speaker||!Array.isArray(m.bindings)||!m.bindings.length||m.bindings.length>100
  ||m.bindings.some((b:any)=>!b||!b.id||typeof b.text!=='string'||!num(b.start)||!num(b.end)||b.start>=b.end||!b.voice_id||!b.dialogue_speaker)
  ||!Array.isArray(m.cues)||!m.cues.length||m.cues.length>100000)return false
 if(m.cues.some((c:any,i:number)=>!c||!num(c.at_seconds)||c.at_seconds<0||!['closed','half','open'].includes(c.pose)||(i>0&&c.at_seconds<=m.cues[i-1].at_seconds)))return false
 return ['closed','half','open'].every(p=>{const f=m.poses?.[p];return f&&sha(f.sha256)&&typeof f.media_url==='string'&&/^(https:\/\/|\/api\/std\/)/.test(f.media_url)&&typeof f.gcs_bucket==='string'&&!!f.gcs_bucket&&typeof f.gcs_path==='string'&&!!f.gcs_path})
}
export function mouthMatchesRecording(m:any,project:any,rows:any[]):boolean {
 const p=project.project_payload||project
 return validWuxiaMouth(m)&&p.subtitle_source_audio_id===m.audio_asset_id&&m.bindings.every((b:any)=>rows.some(r=>
  r.id===b.id&&r.text===b.text&&r.voice_id===b.voice_id&&r.dialogue_kind==='dialogue'&&r.dialogue_speaker===b.dialogue_speaker
  &&Math.abs(Number(r.start_num??r.start_time??r.start)-b.start)<.001&&Math.abs(Number(r.end_num??r.end_time??r.end)-b.end)<.001))
}
export function wuxiaMouthFrame(state:any,graphics:any[],project:any,rows:any[],seconds:number) {
 return stateMouths(state).flatMap((m:any,index:number)=>{
  if(!m?.enabled||m.source_sha256!==state.sha256||!mouthMatchesRecording(m,project,rows)
   ||!m.bindings.some((b:any)=>seconds>=b.start&&seconds<b.end)
   ||!graphics.some(g=>g.kind==='speech_bubble'&&g.speaker===m.speaker&&m.block_ids.includes(g.block_id)))return []
  let lo=0,hi=m.cues.length-1
  while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(m.cues[mid].at_seconds<=seconds+1e-7)lo=mid;else hi=mid-1}
  if(m.cues[lo].at_seconds>seconds)return []
  const pose=m.cues[lo].pose
  return [{mouth:m,index,pose,frame:m.poses[pose]}]
 })
}
export function hasWuxiaMouths(project:any):boolean {
 return Boolean(project.project_payload?.structure?.wuxia_ae_package?.scenes?.some((s:any)=>s.states?.some((state:any)=>stateMouths(state).some((m:any)=>m&&m.enabled!==false))))
}
