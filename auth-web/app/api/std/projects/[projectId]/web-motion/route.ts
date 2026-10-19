import { NextResponse } from 'next/server'
import { createHash } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { loadStdProjectAssets } from '@/lib/stdProjectAssets'
import { selectNarrationAsset } from '@/lib/stdContentIdentity'
import { lipSyncPlan, lipSyncSceneStarts } from '@/lib/stdLipSync'
import { aeSceneSources } from '@/lib/stdAeScenePreparation'
import { storageSourceForAsset } from '@/lib/stdSceneMedia'
import { selectedVideoModel } from '@/lib/stdVideoModelStore'
import { createProviderVideo,pollProviderVideo,outputVideoUrl } from '@/lib/stdMotionVideoProvider'
import { createGcsSignedReadUrl, getGcsObjectMetadata, downloadGcsObjectViaSignedUrl } from '@/lib/gcsStorage'
import {backgroundWindow,backgroundVolume} from '@/lib/stdAudioMix'
import {resolveSfxCues,sfxNeedsReview} from '@/lib/stdSfxCues'
import {templateOverlayPng} from '@/lib/stdTemplateOverlayPng'
import {motionProductionMethod} from '@/lib/stdMotionStudio'
import {linkedWebPsd,linkedWebPsdSources} from '@/lib/stdWebMotionSources'

export const dynamic='force-dynamic'
export const maxDuration=60
const fileUrl=(project:string,asset:any)=>`/api/std/projects/${project}/assets/file?assetId=${encodeURIComponent(asset.id)}`
async function context(req:Request,id:string){
    const auth=await requireStdUser(req);if(!auth.ok)return {response:auth.response}
    const p=await db.from('std_projects').select('*').eq('id',id).eq('employee_email',auth.requester.email).maybeSingle()
    if(p.error)throw p.error;if(!p.data)return {response:NextResponse.json({error:'프로젝트를 찾을 수 없습니다.'},{status:404})}
    const assets=await loadStdProjectAssets(db,id,'*');if(assets.error)throw assets.error
    return {project:p.data,assets:assets.data||[]}
}
export async function GET(req:Request,{params}:{params:{projectId:string}}){
    try{
        const c=await context(req,params.projectId);if(c.response)return c.response
        const settings={...c.project.project_payload?.settings,...c.project.project_payload?.render_settings}
        const psdId=new URL(req.url).searchParams.get('psd')
        if(psdId){
            const asset=c.assets!.find(a=>a.id===psdId),source=linkedWebPsd(params.projectId,asset)
            if(!source)throw Error('이 프로젝트의 검수된 PSD 원본이 필요합니다.')
            const metadata=await getGcsObjectMetadata({bucket:source.gcsBucket,objectPath:source.gcsPath})
            if(metadata.size>150*1024*1024)throw Error('PSD는 150MB 이하로 준비해 주세요.')
            const file=await downloadGcsObjectViaSignedUrl({bucket:source.gcsBucket,objectPath:source.gcsPath})
            if(file.buffer.length>150*1024*1024||createHash('sha256').update(file.buffer).digest('hex')!==source.sha256)throw Error('PSD 원본 해시가 검수 기록과 다릅니다.')
            return new Response(new Uint8Array(file.buffer),{headers:{'Content-Type':'image/vnd.adobe.photoshop','Cache-Control':'private, no-store'}})
        }
        if(new URL(req.url).searchParams.get('template')==='1'){
            const png=await templateOverlayPng(settings);if(!png)throw Error('저장된 템플릿 오버레이를 확인해 주세요.')
            return new Response(new Uint8Array(png),{headers:{'Content-Type':'image/png','Cache-Control':'private, no-store'}})
        }
        const jobId=new URL(req.url).searchParams.get('video')
        if(jobId){
            const job=c.assets!.find(a=>a.id===jobId&&a.metadata?.kind==='web_motion_ai'),url=job?.metadata?.output_url
            if(!url)throw Error('완료된 영상 생성 작업이 필요합니다.')
            const response=await fetch(outputVideoUrl({output:url}),{redirect:'error',signal:AbortSignal.timeout(45000)})
            if(!response.ok||!response.headers.get('content-type')?.startsWith('video/'))throw Error('생성 영상을 읽을 수 없습니다.')
            return new Response(response.body,{headers:{'Content-Type':response.headers.get('content-type')!,'Cache-Control':'private, no-store'}})
        }
        const scenes=await db.from('std_project_scenes').select('*').eq('project_id',params.projectId).order('scene_number');if(scenes.error)throw scenes.error
        const active=c.assets!.filter(a=>['uploaded','assigned'].includes(a.status)).sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at))),psds=aeSceneSources(active),linkedPsds=linkedWebPsdSources(params.projectId,active,psds)
        let audio:any=null,subtitles:any[]=[],starts:number[]=[],audioError=''
        try{lipSyncPlan(c.project,scenes.data||[],active);audio=selectNarrationAsset(c.project,active);subtitles=audio.metadata.subtitle_timeline;starts=lipSyncSceneStarts(c.project,scenes.data||[],audio)}catch(e:any){audioError=e.message}
        const sounds:any[]=[],total=Number(subtitles.at(-1)?.end)||0,bgmId=settings.bgm_asset_id||c.project.project_payload?.bgm_asset_id
        const bgm=active.find(a=>a.id===bgmId)
        if(bgmId){const window=backgroundWindow(settings,subtitles,total);if(!bgm||!window.valid)audioError=audioError||'저장된 배경음·구간을 확인해 주세요.';else sounds.push({url:fileUrl(params.projectId,bgm),...window,volume:backgroundVolume(settings.bgm_volume),loop:settings.bgm_loop!==false})}
        const cues=(settings.sfx_cues||c.project.project_payload?.sfx_cues||[]).filter((c:any)=>c.enabled!==false)
        if(cues.some((c:any)=>sfxNeedsReview(c,subtitles)))audioError=audioError||'효과음 기준 자막이 변경되었습니다. 효과음 구간을 확인해 주세요.'
        for(const cue of resolveSfxCues(cues,subtitles)){const asset=active.find(a=>a.id===cue.asset_id);if(!asset){audioError=audioError||'저장된 효과음을 확인해 주세요.';continue}sounds.push({url:fileUrl(params.projectId,asset),start:Number(cue.start),end:Math.min(total,Number(cue.start)+Number(cue.duration||asset.metadata?.duration_seconds||3)),volume:Number(cue.volume??.5),loop:false,fadeIn:0,fadeOut:.05})}
        return NextResponse.json({audio:audio?{id:audio.id,url:fileUrl(params.projectId,audio)}:null,audio_error:audioError,subtitles,sounds,
            overlay:settings.std_template_overlay_png_data_url||settings.std_template_overlay_gcs?`/api/std/projects/${params.projectId}/web-motion?template=1`:null,
            scenes:(scenes.data||[]).map((s,i)=>{const linked=!psds.has(s.scene_number)&&linkedPsds.get(s.scene_number),candidate=psds.get(s.scene_number)||linked||active.find(a=>a.scene_number===s.scene_number&&a.asset_type==='image')||active.find(a=>a.scene_number===s.scene_number&&a.asset_type==='video'&&!a.metadata?.ae_mouth_fingerprint)
                return {number:s.scene_number,title:s.scene_title,start:starts[i],end:starts[i+1]??subtitles.at(-1)?.end,source:candidate?{id:candidate.id,kind:linked||/\.psd$/i.test(candidate.file_name)?'psd':candidate.asset_type,url:linked?`/api/std/projects/${params.projectId}/web-motion?psd=${encodeURIComponent(candidate.id)}`:fileUrl(params.projectId,candidate)}:null}}),
            ai_jobs:active.filter(a=>a.metadata?.kind==='web_motion_ai').map(a=>({id:a.id,number:a.scene_number,state:a.metadata.state})),
            finals:active.filter(a=>a.asset_type==='video'&&a.scene_number==null&&String(a.file_name).startsWith('motion-web-final-')).slice(0,20).map(a=>({id:a.id,name:a.file_name,url:fileUrl(params.projectId,a),created_at:a.created_at})),
        },{headers:{'Cache-Control':'private, no-store'}})
    }catch(e:any){return NextResponse.json({error:e.message},{status:400})}
}
export async function POST(req:Request,{params}:{params:{projectId:string}}){
    try{
        const c=await context(req,params.projectId);if(c.response)return c.response
        const body=await req.json()
        if(motionProductionMethod(c.project)!=='motion_studio')throw Error('Motion Studio 추가 옵션을 선택하고 저장한 뒤 사용해 주세요. 현재는 기존 AE 제작 방식입니다.')
        if(['approved','canceled'].includes(c.project.status))throw Error('종료된 프로젝트입니다.')
        if(body.action==='review'){
            const asset=c.assets!.find(a=>a.id===body.asset_id&&a.asset_type==='video'&&a.scene_number==null&&a.status==='uploaded')
            if(!asset||!asset.file_name.startsWith('motion-web-final-'))throw Error('웹에서 제작한 최종 영상 파일이 필요합니다.')
            const source=storageSourceForAsset(asset);if(!source)throw Error('영상 저장 위치를 확인해 주세요.')
            const receipt=await db.from('remote_render_queue').select('id').eq('id',asset.id).maybeSingle();if(receipt.error)throw receipt.error
            if(receipt.data&&c.project.status==='review_requested'&&c.project.progress_payload?.remote_render_queue_id===asset.id)return NextResponse.json({render_queue_id:asset.id})
            if(c.project.submitted_at||c.project.status==='review_requested')throw Error('이미 제출된 프로젝트입니다. 현재 검수 요청을 먼저 확인해 주세요.')
            if(!receipt.data){
                const inserted=await db.from('remote_render_queue').insert({id:asset.id,project_id:1900000000,project_name:c.project.title,email:c.project.employee_email,status:'completed',progress:100,
                    message:'웹 모션 제작 완료 · 관리자 실제 영상 검수 필요',completed_at:new Date().toISOString(),render_mode:'gcs_api',result_file_id:`gs://${source.gcsBucket}/${source.gcsPath}`,result_file_name:asset.file_name,
                    metadata:{std_web_project_id:c.project.id,topic_queue_id:c.project.topic_queue_id,gcs_bucket:source.gcsBucket,gcs_path:source.gcsPath,web_motion_asset_id:asset.id,renderer:'browser_canvas_webcodecs',admin_publish_status:'pending_review',admin_action_required:'review_and_upload',output_review:{passed:false,status:'pending_admin_review'}}})
                if(inserted.error&&inserted.error.code!=='23505')throw inserted.error
            }
            const updated=await db.from('std_projects').update({status:'review_requested',submitted_at:new Date().toISOString(),updated_at:new Date().toISOString(),progress_payload:{...c.project.progress_payload,remote_render_queue_id:asset.id,postprocess_status:'complete',admin_publish_status:'pending_review'}}).eq('id',c.project.id).eq('updated_at',c.project.updated_at).select('id').maybeSingle()
            if(updated.error||!updated.data)throw Error('프로젝트가 변경되었습니다. 새로고침 후 검수 요청 상태를 확인해 주세요.')
            return NextResponse.json({render_queue_id:asset.id})
        }
        if(c.project.submitted_at||c.project.status==='review_requested')throw Error('제출 전 프로젝트에서 작업해 주세요.')
        if(!['generate','poll'].includes(body.action))throw Error('지원하지 않는 작업입니다.')
        const number=Number(body.scene_number)
        if(!Number.isInteger(number)||number<1)throw Error('씬 번호를 확인해 주세요.')
        if(body.action==='poll'){
            const job=c.assets!.find(a=>a.id===body.job_id&&a.metadata?.kind==='web_motion_ai'&&a.scene_number===number)
            if(!job?.metadata.request)throw Error('기존 생성 요청의 접수 여부를 확인해야 합니다. 자동으로 재요청하지 않습니다.')
            const selected=await selectedVideoModel(c.project.employee_email,job.metadata.model_id)
            if(selected.fingerprint!==job.metadata.model_fingerprint)throw Error('생성 요청 후 모델 설정이 변경됐습니다.')
            const result=job.metadata.output_url?{state:'complete',url:job.metadata.output_url}:await pollProviderVideo(selected.config,selected.secret,job.metadata.request)
            if(result.state==='complete'){
                const saved=await db.from('std_project_assets').update({metadata:{...job.metadata,state:'complete',output_url:result.url},updated_at:new Date().toISOString()}).eq('id',job.id)
                if(saved.error)throw saved.error
            }
            return NextResponse.json({id:job.id,state:result.state,...(result.state==='complete'?{url:`/api/std/projects/${params.projectId}/web-motion?video=${job.id}`}:{})})
        }
        if(body.mode!=='hybrid')throw Error('AI 영상 생성은 혼합 모드에서만 사용할 수 있습니다.')
        const duration=Number(body.duration),prompt=String(body.prompt||'').trim()
        if(![3,4,5].includes(duration)||!prompt||prompt.length>4000)throw Error('3~5초 길이와 연출 내용을 확인해 주세요.')
        const source=c.assets!.find(a=>a.id===body.source_asset_id&&a.scene_number===number&&['image','original'].includes(a.asset_type)&&['uploaded','assigned'].includes(a.status)&&a.mime_type?.startsWith('image/')&&!/\.psd$/i.test(a.file_name))
        const ref=storageSourceForAsset(source);if(!ref)throw Error('이 씬의 이미지 원본을 먼저 저장해 주세요.')
        const object=await getGcsObjectMetadata({bucket:ref.gcsBucket,objectPath:ref.gcsPath})
        if(object.size>12_000_000||!object.contentType.startsWith('image/'))throw Error('AI 영상 원본 이미지는 12MB 이하로 준비해 주세요.')
        const pixels=await downloadGcsObjectViaSignedUrl({bucket:ref.gcsBucket,objectPath:ref.gcsPath})
        const sourceHash=createHash('sha256').update(pixels.buffer).digest('hex')
        const selected=await selectedVideoModel(c.project.employee_email)
        const fingerprint=createHash('sha256').update(JSON.stringify([c.project.id,number,sourceHash,prompt,duration,selected.fingerprint])).digest('hex')
        const existing=c.assets!.find(a=>a.metadata?.kind==='web_motion_ai'&&a.metadata.fingerprint===fingerprint)
        if(existing)return NextResponse.json({id:existing.id,state:existing.metadata.state})
        const id=`${fingerprint.slice(0,8)}-${fingerprint.slice(8,12)}-5${fingerprint.slice(13,16)}-a${fingerprint.slice(17,20)}-${fingerprint.slice(20,32)}`
        const metadata={kind:'web_motion_ai',state:'creating',fingerprint,model_id:selected.config.id,model_fingerprint:selected.fingerprint,source_asset_id:source.id,duration}
        const reserved=await db.from('std_project_assets').insert({id,project_id:c.project.id,scene_number:number,asset_type:'other',status:'uploaded',file_name:`web-motion-ai-${number}.json`,metadata})
        if(reserved.error){if(reserved.error.code==='23505')return NextResponse.json({id,state:'creating'});throw reserved.error}
        try{
            const url=await createGcsSignedReadUrl({bucket:ref.gcsBucket,objectPath:ref.gcsPath,expiresInMinutes:60})
            const request=await createProviderVideo(selected.config,selected.secret,{prompt,duration},url)
            const saved=await db.from('std_project_assets').update({metadata:{...metadata,state:'submitted',request},updated_at:new Date().toISOString()}).eq('id',id)
            if(saved.error)throw saved.error
            return NextResponse.json({id,state:'pending'})
        }catch{
            await db.from('std_project_assets').update({metadata:{...metadata,state:'needs_reconcile'},updated_at:new Date().toISOString()}).eq('id',id)
            return NextResponse.json({id,error:'생성 요청의 접수 여부 확인이 필요합니다. 중복 결제를 피하기 위해 다시 요청하지 않습니다.'},{status:409})
        }
    }catch(e:any){return NextResponse.json({error:e.message},{status:400})}
}
