import { createHash } from 'crypto'
import { motionForProject, motionProductionMethod } from './stdMotionStudio'
import { selectNarrationAsset } from './stdContentIdentity'
import { lipSyncPlan, lipSyncSceneStarts } from './stdLipSync'
import { storageSourceForAsset } from './stdSceneMedia'

export const horizontalWebtoon = (project:any) => motionForProject(project)?.edit_mode === 'horizontal_webtoon'
export function validateWebtoonPlan(plan:any) {
    const rect=(r:any)=>Array.isArray(r)&&r.length===4&&r.every((n:any)=>typeof n==='number'&&Number.isFinite(n))&&r[0]>=0&&r[1]>=0&&r[2]>.01&&r[3]>.01&&r[0]+r[2]<=1.000001&&r[1]+r[3]<=1.000001
    if(plan?.version!==1||!Array.isArray(plan.shots)||!plan.shots.length||plan.shots.length>32||!Array.isArray(plan.evidence)||!plan.evidence.length||plan.evidence.some((s:any)=>typeof s!=='string'||!s.trim()||s.length>2000))throw Error('웹툰 컷 분석·시각 근거가 없습니다.')
    let cursor=0
    for(const shot of plan.shots){
        if(typeof shot.start!=='number'||typeof shot.end!=='number'||!Number.isFinite(shot.start+shot.end)||Math.abs(shot.start-cursor)>1e-6||shot.end<=shot.start||shot.end>1||!Array.isArray(shot.panels)||shot.panels.length<1||shot.panels.length>3)throw Error('웹툰 컷 시간에 누락·중복이 있습니다.')
        for(const p of shot.panels)if(!rect(p.crop)||!rect(p.frame)||typeof p.reveal!=='number'||!Number.isFinite(p.reveal)||p.reveal<0||p.reveal>=1||![p.zoom_from,p.zoom_to].every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=1&&n<=1.15))throw Error('웹툰 원본·화면 영역과 등장 시점을 확인해 주세요.')
        if(!shot.panels.some((p:any)=>p.reveal===0))throw Error('각 컷 시작에는 원본이 보여야 합니다.')
        for(let i=0;i<shot.panels.length;i++)for(let j=i+1;j<shot.panels.length;j++){
            const a=shot.panels[i].frame,b=shot.panels[j].frame
            if(Math.min(a[0]+a[2],b[0]+b[2])-Math.max(a[0],b[0])>1e-6&&Math.min(a[1]+a[3],b[1]+b[3])-Math.max(a[1],b[1])>1e-6)throw Error('웹툰 화면의 컷이 겹칩니다.')
        }
        cursor=shot.end
    }
    if(cursor!==1)throw Error('웹툰 연출이 음성 전체 구간을 포함해야 합니다.')
    return plan
}
export function webtoonInputs(project:any,scenes:any[],assets:any[]) {
    const motion=motionForProject(project)
    if(!horizontalWebtoon(project)||motionProductionMethod(project)!=='ae'||motion?.aspect!=='16:9')throw Error('가로 웹툰 컷 모드를 저장해 주세요.')
    if(project.project_payload?.lipsync?.enabled)throw Error('가로 웹툰 컷 모드는 원본 말풍선을 유지합니다. 립싱크를 끈 뒤 준비해 주세요.')
    lipSyncPlan(project,scenes,assets)
    const audio=selectNarrationAsset(project,assets),timeline=audio.metadata.subtitle_timeline
    const starts=lipSyncSceneStarts(project,scenes,audio),total=timeline.at(-1)?.end
    return scenes.map((scene,i)=>{
        const number=Number(scene.scene_number)
        const choices=assets.filter(a=>Number(a.scene_number)===number&&['uploaded','assigned'].includes(a.status)&&storageSourceForAsset(a)).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)))
        const asset=choices.find(a=>a.asset_type==='original'&&/\.psd$/i.test(a.file_name||''))||choices.find(a=>a.asset_type==='image')
        if(!asset)throw Error(`${number}번 씬에 원본 이미지 또는 PSD를 등록해 주세요.`)
        const start=i===0?0:starts[i],end=starts[i+1]??total
        if(!Number.isFinite(start+end)||end<=start)throw Error(`${number}번 씬의 확정 음성 구간을 확인해 주세요.`)
        const subtitles=timeline.flatMap((t:any,index:number)=>Number(project.project_payload.subtitles[index]?.scene_number)===number?[{text:t.text,start:Math.max(0,t.start-start),end:Math.min(end-start,t.end-start)}]:[])
        const input={version:1,task:'direction',horizontal_webtoon:true,aspect:'16:9',fps:motion!.fps,asset,scene:{number},duration:end-start,subtitles,audio_identity:{id:audio.id,fingerprint:createHash('sha256').update(JSON.stringify(audio.metadata)).digest('hex')},start,end}
        const fingerprint=createHash('sha256').update(JSON.stringify(input)).digest('hex')
        return {number,input,fingerprint,asset,start,end}
    })
}
export function readyWebtoonPlan(item:ReturnType<typeof webtoonInputs>[number],assets:any[]) {
    const job=assets.find(a=>a.metadata?.kind==='motion_preview'&&a.metadata.fingerprint===item.fingerprint&&a.metadata.state==='ready')
    const suggestion=job?.metadata?.suggestion
    if(!suggestion?.webtoon||!job.metadata.source_sha256)throw Error(`${item.number}번 가로 웹툰 컷 연출을 대본워커에서 준비해 주세요.`)
    validateWebtoonPlan(suggestion.webtoon)
    if(suggestion.webtoon.shots.some((s:any)=>(s.end-s.start)*(item.end-item.start)<.25))throw Error(`${item.number}번 컷이 너무 짧습니다. 연출을 다시 준비해 주세요.`)
    return {plan:suggestion.webtoon,source_sha256:job.metadata.source_sha256,job_id:job.id}
}
