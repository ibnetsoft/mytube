// A different final-audio asset ID does not invalidate unchanged recorded scenes.
// This is candidate eligibility only. The worker must compare the decoded recordings
// and inspect the actual output before it can approve a reused mouth clip.
export function recordedMotionSourceReuse(project:any,asset:any,assets:any[],audio:any) {
    const m=asset?.metadata||{},number=Number(asset?.scene_number)
    if(asset?.project_id!==project.id||asset.asset_type!=='video'||!['uploaded','assigned'].includes(asset.status)
        ||!m.ae_mouth_fingerprint||m.lipsync_fingerprint||m.kind==='mouth_preview'||m.timing_mode!=='final_voice'
        ||m.voice_synced!==true||m.artifact_ready!==true||!/^[a-f0-9]{64}$/.test(m.render_sha256||''))return null
    const job=assets.find(a=>a.project_id===project.id&&a.metadata?.kind==='ae_mouth_job'
        &&a.metadata.fingerprint===m.ae_mouth_fingerprint&&a.metadata.input?.audio?.id===m.source_audio_id)
    const input=job?.metadata?.input,prior=input?.scenes?.find((s:any)=>Number(s.number)===number)
    const image=assets.find(a=>a.project_id===project.id&&a.asset_type==='image'&&Number(a.scene_number)===number
        &&['uploaded','assigned'].includes(a.status))
    if(!prior||!image||image.id!==m.source_image_id||prior.image?.id!==image.id)return null
    const timeline=audio?.metadata?.subtitle_timeline||[]
    const current=(project.project_payload?.subtitles||[]).flatMap((s:any,index:number)=>Number(s.scene_number)===number
        ?[{text:String(s.text||''),voice_id:timeline[index]?.voice_id,direction:String(s.direction||''),
            kind:s.dialogue_kind||'',start:timeline[index]?.start,end:timeline[index]?.end}]:[])
    const old=(input.subtitles||[]).filter((s:any)=>Number(s.scene_number)===number)
    const start=current[0]?.start,end=current.at(-1)?.end,oldStart=Number(prior.start),oldEnd=Number(prior.end)
    if(!current.length||current.length!==old.length||![start,end,oldStart,oldEnd,Number(m.duration_seconds)].every(Number.isFinite)
        ||Math.abs(end-start-(oldEnd-oldStart))>0.001||Math.abs(Number(m.duration_seconds)-(end-start))>0.001)return null
    if(current.some((s:any,i:number)=>s.text!==old[i].text||s.voice_id!==old[i].voice_id||s.direction!==old[i].direction
        ||s.kind!==old[i].kind||Math.abs(s.start-start-(old[i].start-oldStart))>0.001
        ||Math.abs(s.end-start-(old[i].end-oldStart))>0.001))return null
    const oldAudio=input.audio,stored=oldAudio.metadata||{}
    const reference={id:oldAudio.id,file_name:oldAudio.file_name,metadata:Object.fromEntries(
        ['storage_provider','storage_bucket','storage_path','gcs_bucket','gcs_path','sha256'].filter(k=>stored[k]!=null).map(k=>[k,stored[k]]))}
    return {version:1,source_asset_id:asset.id,source_sha256:m.render_sha256,audio:reference,
        start:oldStart,end:oldEnd,current_audio_id:audio.id,current_start:start,current_end:end,
        subtitles:current.map((s:any)=>({...s,start:s.start-start,end:s.end-start})),
        verification:'recorded_scene_identity_pending_pcm_and_output_review'}
}
