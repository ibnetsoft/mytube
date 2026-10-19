import { createHash, randomUUID } from 'crypto'
import { supabaseAdmin as db } from './supabaseAdmin'
import { motionForProject } from './stdMotionStudio'
import { aeSceneSources } from './stdAeScenePreparation'
import { selectNarrationAsset } from './stdContentIdentity'
import { lipSyncPlan, lipSyncSceneStarts, reviewedLipSyncAssets } from './stdLipSync'
import { storageSourceForAsset } from './stdSceneMedia'
import { backgroundWindow } from './stdAudioMix'
import { sfxNeedsReview, resolveSfxCues } from './stdSfxCues'
import { persistTemplateOverlay, templateOverlayPng } from './stdTemplateOverlayPng'
import { selectedVideoModel } from './stdVideoModelStore'

export function motionAutomationEnabled(project:any) { const m=motionForProject(project);return Boolean(m?.enabled && m.automation) }
export async function registerMotionAutomation(project:any,scenes:any[],assets:any[],userId:string) {
    const motion=motionForProject(project)!
    if(!motion?.enabled || !motion.automation)throw new Error('자동 제작 모드를 선택해 주세요.')
    lipSyncPlan(project,scenes,assets) // Exact finalized voice, script, cast and timing identity.
    const audio=selectNarrationAsset(project,assets)
    if(!storageSourceForAsset(audio))throw new Error('확정 음성을 저장한 뒤 제출해 주세요.')
    const starts=lipSyncSceneStarts(project,scenes,audio),timeline=audio.metadata.subtitle_timeline
    const total=Number(timeline.at(-1)?.end)
    const active=assets.filter(a=>['uploaded','assigned'].includes(a.status)).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)))
    const psds=aeSceneSources(active)
    const lipSync=reviewedLipSyncAssets(project,scenes,assets)
    const verticalOriginal=(project.project_payload?.render_settings?.comic||project.project_payload?.structure?.comic_plan?.render_settings)?.mode==='webtoon_video'
    const ordered=scenes.map((scene,index)=>{
        const n=Number(scene.scene_number)
        const candidates=active.filter(a=>Number(a.scene_number)===n && !a.metadata?.ae_mouth_fingerprint && !a.metadata?.lipsync_fingerprint)
        const image=candidates.find(a=>a.asset_type==='image'),video=candidates.find(a=>a.asset_type==='video')
        const choice=motion.scenes[String(n)]?.source||'auto'
        const selected=choice==='psd'?psds.get(n):choice==='image'?image:choice==='video'?video:psds.get(n)||(verticalOriginal?image||video:video||image)
        const source=lipSync.get(n)||selected
        if(!source||!storageSourceForAsset(source))throw new Error(`${n}번 씬의 이미지·영상 또는 원본 PSD가 필요합니다.`)
        const start=index===0?0:starts[index],end=starts[index+1]??total
        if(!Number.isSafeInteger(n)||n<1||scenes.slice(0,index).some(s=>Number(s.scene_number)===n)||!Number.isFinite(start)||!Number.isFinite(end)||end-start<1/motion.fps)throw new Error(`${n}번 씬의 최종 음성 구간이 유효하지 않습니다.`)
        return {number:n,text:scene.scene_text||'',title:scene.scene_title||'',direction:motion.scenes[String(n)]?.direction||'',start,end,source,source_kind:source.asset_type==='original'?'psd':source.asset_type}
    })
    const settings=await persistTemplateOverlay(project.id,{...project.project_payload?.settings,...project.project_payload?.render_settings})
    await templateOverlayPng(settings)
    const subtitles=project.project_payload.subtitles.map((row:any,index:number)=>({...row,start:timeline[index].start,end:timeline[index].end}))
    const bgmId=settings.bgm_asset_id||project.project_payload.bgm_asset_id
    if(bgmId)settings.bgm_asset_id=bgmId
    if(bgmId&&!backgroundWindow(settings,subtitles,total).valid)throw new Error('배경음 구간을 확인해 주세요.')
    const cues=(settings.sfx_cues||project.project_payload.sfx_cues||[]).filter((c:any)=>c.enabled!==false)
    if(cues.some((c:any)=>sfxNeedsReview(c,subtitles)))throw new Error('효과음 구간을 확인해 주세요.')
    const soundIds=new Set([bgmId,...cues.map((c:any)=>c.asset_id)])
    const sounds=active.filter(a=>soundIds.has(a.id))
    if([...soundIds].filter(Boolean).some(id=>!sounds.some(a=>a.id===id)))throw new Error('선택한 배경음·효과음 파일을 확인해 주세요.')
    const selected=motion.automation.mode==='hybrid'?await selectedVideoModel(project.employee_email):null
    const snapshot={version:1,project:{id:project.id,employee_email:project.employee_email},motion,settings,subtitles,audio,scenes:ordered,sounds,sfx_cues:resolveSfxCues(cues,subtitles),
        model_ref:selected?{id:selected.config.id,fingerprint:selected.fingerprint,config:selected.config}:null}
    const snapshot_json=JSON.stringify(snapshot)
    if(Buffer.byteLength(snapshot_json)>4_000_000)throw new Error('제출 데이터가 너무 큽니다.')
    const fingerprint=createHash('sha256').update(snapshot_json).digest('hex')
    const manifest={version:1,project:{id:project.id},automation:{snapshot_json,fingerprint}}
    const result=await db.rpc('register_std_motion_pipeline',{p_project_id:project.id,p_user_id:userId,p_updated_at:project.updated_at,
        p_run_id:randomUUID(),p_job_id:randomUUID(),p_manifest:manifest,p_hash:fingerprint})
    if(result.error)throw result.error
    return result.data
}
