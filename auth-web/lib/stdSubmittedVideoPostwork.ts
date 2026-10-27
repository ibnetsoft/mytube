import { mouthWorkScenes } from './stdMouthWorkPolicy'
import { subtitleDialogueSpeakerName } from './stdDialogueSceneIndex'
import { coordinateCast, coordinateImage, savedSpeakerGeometry } from './stdSpeakerGeometry'
import { motionProductionMethod, defaultMotionDraft } from './stdMotionStudio'

export const VIDEO_POSTWORK_CONTRACT = 'submitted_video_postwork/v1'
export function originalPostworkVideo(asset:any) {
    const m=asset?.metadata||{}
    return asset?.asset_type==='video' && ['uploaded','assigned'].includes(asset.status) && !m.ae_mouth_fingerprint && !m.lipsync_fingerprint && !m.submitted_video_postwork && !m.source_repair && !m.motion_source_repair && !['repaired_source_clip','motion_source_repair'].includes(m.kind)
}
export function hasSubmittedVideoPostwork(project:any,scenes:any[],assets:any[]) {
    if(motionProductionMethod(project)!=='ae' || project.project_payload?.render_settings?.motion?.edit_mode==='horizontal_webtoon')return false
    const numbers=new Set(scenes.map(s=>Number(s.scene_number)).filter(n=>n>=1&&n<=18))
    return assets.some(a=>numbers.has(Number(a.scene_number))&&originalPostworkVideo(a))
}
export function postworkMotion(project:any) {
    const draft=defaultMotionDraft(project.project_payload?.render_settings?.motion)
    return {...draft,enabled:true,production_method:'ae' as const,automation:{mode:'ae_only' as const,max_ai_clips:1,max_ai_seconds:5}}
}
export function freezeVideoPostwork(project:any,number:number,source:any,rows:any[],assets:any[],creative:any) {
    if(number<1||number>18||!originalPostworkVideo(source))return null
    const dialogue=rows.filter(r=>r.dialogue_kind==='dialogue'&&String(r.text||'').trim()).map(r=>({...r,kind:'dialogue',speaker:subtitleDialogueSpeakerName(r)}))
    if(dialogue.some(r=>!r.speaker))throw Error(`${number}번 영상 대사의 화자를 지정한 뒤 제출하세요.`)
    const reference=coordinateImage(assets,number)
    // An unrelated generation still must never seed coordinates on the uploaded video.
    const videoBound=reference?.metadata?.source_video_sha256 && (reference.metadata.source_video_id===source.id || reference.metadata.source_video_sha256===(source.metadata?.sha256||source.metadata?.render_sha256))
    const regions=videoBound?savedSpeakerGeometry(assets,coordinateCast(project),{number,image:reference,rows:dialogue.map(r=>({speaker:r.speaker}))}):null
    const saved=creative?.submitted_video_postwork
    return {contract:VIDEO_POSTWORK_CONTRACT,source_video_id:source.id,mouth_required:dialogue.length>0,dialogue,
        cast:coordinateCast(project),image:videoBound?reference:null,speaker_regions:regions||null,
        requested_effects:saved?.effects||[],transition:saved?.transition||null,
        playback_rate:1,preserve_source_motion:true,review_required:true,failure_policy:'needs_review',
        source_preparation:'local_codex_actual_submitted_video'}
}
export function postworkDirection(sourceKind:string,postwork:any) {
    return {source:sourceKind,fit:'contain',direction:'제출 원본 영상의 동작·1배속·확정 음성을 유지하고 대본에 근거한 입모양·반딧불·전환만 후작업',
        keys:[0,1].map(t=>({t,x:.5,y:.5,scale:1,rotation:0,opacity:100})),effects:[],transition:'cut'}
}

export function submittedPostworkSummary(project:any,scenes:any[],assets:any[]) {
    const job=project.submitted_at?[...assets].filter(a=>a.metadata?.kind==='motion_automation'&&['uploaded','assigned'].includes(a.status)&&(!project.progress_payload?.motion_automation_job_id||a.id===project.progress_payload.motion_automation_job_id)).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at))).find(a=>{
        try{return JSON.parse(a.metadata.input?.snapshot_json||'{}').submitted_video_postwork===VIDEO_POSTWORK_CONTRACT}catch{return false}
    }):undefined
    if(!job&&!hasSubmittedVideoPostwork(project,scenes,assets))return null
    const m=job?.metadata||{}
    return {applicable:true,postwork:true,status:m.state||'not_started',phase:m.phase||'',automatic:true,autoPending:['queued','processing'].includes(m.state),error:m.error||'',results:(m.results||[]).map((r:any)=>({number:r.number,status:r.review?.passed===true?'approved':'needs_review',speakers:r.submitted_video_postwork?.speakers||[],direction:'원본 영상 1배속·확정 음성 유지 · AE 후작업 출력 검수',reason:r.reason||''})),
        finalUrl:m.state==='complete'&&m.final?.gcs_path?`/api/std/assets/gcs-file?bucket=${encodeURIComponent(m.final.gcs_bucket)}&path=${encodeURIComponent(m.final.gcs_path)}`:null}
}

export function freezePreparedStillMouth(project:any,number:number,source:any,rows:any[],assets:any[],scenes:any[]=[{scene_number:number}]) {
    if(number<=18||!mouthWorkScenes(project,scenes,assets).has(number))return null
    const dialogue=rows.filter(r=>r.dialogue_kind==='dialogue'&&String(r.text||'').trim()).map(r=>({...r,kind:'dialogue',speaker:subtitleDialogueSpeakerName(r)}))
    if(!dialogue.length)return null
    if(source.asset_type==='video')return null // Existing recording-bound lip-sync is verified by the worker.
    if(source.asset_type!=='image')throw Error(`${number}번 씬의 PSD 장면과 입모양은 함께 선택할 수 없습니다. 준비된 대사 이미지·영상을 확인하세요.`)
    const regions=savedSpeakerGeometry(assets,coordinateCast(project),{number,image:source,rows:dialogue.map(r=>({speaker:r.speaker}))})
    if(dialogue.some(r=>!r.speaker||!regions?.speakers?.some((s:any)=>s.speaker===r.speaker)))throw Error(`${number}번 씬의 기존 입모양 좌표·소재 준비를 완료한 뒤 제출하세요.`)
    return {contract:'prepared_still_mouth/v1',mouth_required:true,dialogue,image:source,speaker_regions:regions,cast:coordinateCast(project)}
}
