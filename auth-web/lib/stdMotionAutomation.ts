import { recordedMotionSourceReuse } from './stdMotionSourceReuse'
import { createHash, randomUUID } from 'crypto'
import { supabaseAdmin as db } from './supabaseAdmin'
import { motionForProject, motionProductionMethod } from './stdMotionStudio'
import effectcraftSource from './effectcraftSource.json'
import ecSupplementalAssetsContract from './ecSupplementalAssetsContract.json'
import { aeSceneSources, preparedAeScenes } from './stdAeScenePreparation'
import { selectNarrationAsset } from './stdContentIdentity'
import { lipSyncPlan, lipSyncSceneStarts, reviewedLipSyncAssets } from './stdLipSync'
import { storageSourceForAsset } from './stdSceneMedia'
import { backgroundWindow } from './stdAudioMix'
import { sfxNeedsReview, resolveSfxCues } from './stdSfxCues'
import { persistTemplateOverlay, templateOverlayPng } from './stdTemplateOverlayPng'
import { selectedVideoModel } from './stdVideoModelStore'
import { assertPreparationFinished } from './stdWorkflowBoundary'
import { bindSceneDirection, directedScene } from './stdSceneExecution'
import { horizontalWebtoon, webtoonInputs, readyWebtoonPlan } from './stdHorizontalWebtoon'

export function motionAutomationEnabled(project:any) { const m=motionForProject(project);return Boolean(m?.enabled && m.automation) }
export async function registerMotionAutomation(project:any,scenes:any[],assets:any[],userId:string,resubmission=false) {
    assertPreparationFinished(assets)
    const motion=motionForProject(project)!
    const horizontal=horizontalWebtoon(project)
    const horizontalInputs=horizontal?webtoonInputs(project,scenes,assets):[]
    const effectcraft=motionProductionMethod(project)==='effectcraft'
    if(effectcraft&&motion.web)throw new Error('브라우저 전용 타임라인·삽입 설정은 EffectCraft로 자동 변환하지 않습니다. 해당 설정은 브라우저 제작 방식에서 사용해 주세요.')
    if(!motion?.enabled || !motion.automation)throw new Error('자동 제작 모드를 선택해 주세요.')
    lipSyncPlan(project,scenes,assets) // Exact finalized voice, script, cast and timing identity.
    const audio=selectNarrationAsset(project,assets)
    if(!storageSourceForAsset(audio))throw new Error('확정 음성을 저장한 뒤 제출해 주세요.')
    const starts=lipSyncSceneStarts(project,scenes,audio),timeline=audio.metadata.subtitle_timeline
    const total=Number(timeline.at(-1)?.end)
    const active=assets.filter(a=>['uploaded','assigned'].includes(a.status)).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)))
    const psds=aeSceneSources(active)
    const prepared=horizontal?new Map<number,any>():preparedAeScenes(project,scenes,assets)
    const lipSync=horizontal?new Map<number,any>():reviewedLipSyncAssets(project,scenes,assets)
    const verticalOriginal=(project.project_payload?.render_settings?.comic||project.project_payload?.structure?.comic_plan?.render_settings)?.mode==='webtoon_video'
    const ordered=scenes.map((scene,index)=>{
        const n=Number(scene.scene_number)
        const candidates=active.filter(a=>storageSourceForAsset(a)&&Number(a.scene_number)===n && (!a.metadata?.ae_mouth_fingerprint || recordedMotionSourceReuse(project,a,assets,audio)) && !a.metadata?.lipsync_fingerprint)
        const image=candidates.find(a=>a.asset_type==='image'),video=candidates.find(a=>a.asset_type==='video')
        const choice=motion.scenes[String(n)]?.source||'auto'
        const selected=effectcraft?(choice==='psd'&&psds.get(n)?psds.get(n):video||image||psds.get(n)):choice==='psd'?psds.get(n):choice==='image'?image:choice==='video'?video:psds.get(n)||(verticalOriginal?image||video:video||image)
        const webtoonInput=horizontalInputs.find(item=>item.number===n)
        const webtoon=webtoonInput?readyWebtoonPlan(webtoonInput,assets):null
        const source=webtoonInput?.asset||lipSync.get(n)||selected
        if(!source||!storageSourceForAsset(source))throw new Error(`${n}번 씬의 이미지·영상 또는 원본 PSD가 필요합니다.`)
        const start=index===0?0:starts[index],end=starts[index+1]??total
        if(!Number.isSafeInteger(n)||n<1||scenes.slice(0,index).some(s=>Number(s.scene_number)===n)||!Number.isFinite(start)||!Number.isFinite(end)||end-start<1/motion.fps)throw new Error(`${n}번 씬의 최종 음성 구간이 유효하지 않습니다.`)
        const preparation=source.asset_type==='original'&&!horizontal?prepared.get(n):null
        if(source.asset_type==='original'&&!horizontal&&!preparation)throw new Error(`${n}번 PSD의 레이어·AE 연출을 대본워커에서 준비한 뒤 제출하세요.`)
        const planned=project.project_payload?.structure?.scenes?.find((s:any)=>Number(s.scene_number||s.scene_order)===n)
        const authored=motion.scenes[String(n)]
        if(effectcraft&&(authored?.finance||authored?.cues?.length||authored?.native?.paths?.length||authored?.native?.effects?.length||Object.values(authored?.layers||{}).some(l=>l.advanced)))throw new Error(`${n}번 씬의 웹 전용 리그·효과는 EffectCraft로 자동 변환하지 않습니다. 브라우저 제작 또는 기존 AE를 선택해 주세요.`)
        const creative=planned?.scene_direction_plan||planned?.ae_directorial_plan||null
        const sourceKind=horizontal?'image':source.asset_type==='original'?'psd':source.asset_type
        const recordedRows=project.project_payload.subtitles.map((row:any,i:number)=>({...row,start:timeline[i].start,end:timeline[i].end})).filter((row:any)=>Number(row.scene_number)===n)
        const reviewedCamera=preparation?.metadata?.result?.plan?.camera
        const executable=directedScene(creative)&&Array.isArray(reviewedCamera)
            ? {...creative,execution_design:{...creative.execution_design,camera:{...creative.execution_design.camera,keys:reviewedCamera.map((k:any)=>({...k,opacity:100}))}}}
            : creative
        const generated=horizontal?null:bindSceneDirection(executable,sourceKind,recordedRows,start,end,motion.fps)
        const explicit=project.project_payload?.render_settings?.motion?.scenes?.[String(n)]
        return {number:n,text:scene.scene_text||'',title:scene.scene_title||'',direction:motion.scenes[String(n)]?.direction||'',
            ...(!horizontal&&directedScene(creative)?{direction_contract:creative.contract}:{}),
            prepared_direction:(!horizontal&&(explicit||generated||motion.scenes[String(n)]))||{source:sourceKind,fit:'contain',direction:horizontal?'고정 가로 웹툰 컷 계획 · 원본 말풍선 유지':'원본 유지',keys:[{t:0,x:.5,y:.5,scale:1,rotation:0,opacity:100},{t:1,x:.5,y:.5,scale:1,rotation:0,opacity:100}],effects:[],transition:'cut'},
            creative_reference:planned?.scene_direction_plan||planned?.ae_directorial_plan||null,
            ...(webtoon?{webtoon}:{}),preparation,start,end,source,...(source.asset_type==='video'&&image?{source_reference_image:image}:{}),...(source.metadata?.ae_mouth_fingerprint?{recorded_source_reuse:recordedMotionSourceReuse(project,source,assets,audio)}:{}),source_kind:sourceKind}
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
    const selected=!effectcraft&&motion.automation.mode==='hybrid'?await selectedVideoModel(project.employee_email):null
    const snapshot={version:1,...(effectcraft?{renderer:{engine:'effectcraft',revision:effectcraftSource.revision,version:effectcraftSource.version}}:horizontal?{renderer:{engine:'ae_horizontal_webtoon',version:1}}:{}),project:{id:project.id,employee_email:project.employee_email},motion:effectcraft?{...motion,automation:{...motion.automation,mode:'ae_only'}}:motion,...(effectcraft?{execution_policy:{review_policy:'skip_user_requested/v1',source_policy:'preserve_uploaded_video/v1',authorization:'default_submission_existing_assets_without_review'}}:{}),settings,subtitles,audio,scenes:ordered,sounds,sfx_cues:resolveSfxCues(cues,subtitles),
        model_ref:selected?{id:selected.config.id,fingerprint:selected.fingerprint,config:selected.config}:null}
    if(effectcraft)Object.assign(snapshot,{supplemental_assets:ecSupplementalAssetsContract})
    const snapshot_json=JSON.stringify(snapshot)
    if(Buffer.byteLength(snapshot_json)>4_000_000)throw new Error('제출 데이터가 너무 큽니다.')
    const fingerprint=createHash('sha256').update(snapshot_json).digest('hex')
    const manifest={version:1,project:{id:project.id},automation:{snapshot_json,fingerprint}}
    if(horizontal&&resubmission)throw Error('가로 웹툰 컷 모드의 재제출은 프로젝트를 다시 열고 준비한 뒤 제출해 주세요.')
    const result=await db.rpc(horizontal?'register_std_horizontal_webtoon_pipeline':resubmission?'register_std_motion_resubmission':effectcraft?'register_std_effectcraft_pipeline':'register_std_motion_pipeline',{p_project_id:project.id,p_user_id:userId,p_updated_at:project.updated_at,
        p_run_id:randomUUID(),p_job_id:randomUUID(),p_manifest:manifest,p_hash:fingerprint,...(resubmission?{p_engine:effectcraft?'effectcraft':'ae'}:{})})
    if(result.error)throw result.error
    return result.data
}
