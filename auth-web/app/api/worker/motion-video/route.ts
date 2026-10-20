import { createHash,timingSafeEqual } from 'crypto'
import { NextResponse } from 'next/server'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { selectedVideoModel } from '@/lib/stdVideoModelStore'
import { createGcsSignedReadUrl } from '@/lib/gcsStorage'
import { createProviderVideo,pollProviderVideo } from '@/lib/stdMotionVideoProvider'
export const dynamic='force-dynamic'
export const maxDuration=60
export async function POST(req:Request) {
    const expected=process.env.SUPABASE_SERVICE_ROLE_KEY||'',supplied=(req.headers.get('authorization')||'').replace(/^Bearer /,'')
    if(!expected||Buffer.byteLength(expected)!==Buffer.byteLength(supplied)||!timingSafeEqual(Buffer.from(expected),Buffer.from(supplied)))return NextResponse.json({error:'Unauthorized'},{status:401})
    try {
        const body=await req.json()
        const result=await db.from('std_project_assets').select('*').eq('id',String(body.job_id)).maybeSingle()
        if(result.error)throw result.error
        const job=result.data,m=job?.metadata
        if(!['motion_automation','effectcraft_automation'].includes(m?.kind)||m.state!=='processing'||m.worker_token!==body.worker_token)throw Error('유효한 자동 제작 워커 임대가 필요합니다.')
        const frozen=m.input
        if(createHash('sha256').update(frozen.snapshot_json).digest('hex')!==frozen.fingerprint)throw Error('제출 원본 검증값이 다릅니다.')
        const input=JSON.parse(frozen.snapshot_json),number=Number(body.scene_number)
        if(input.motion.automation?.mode!=='hybrid'||!input.model_ref)throw Error('AE 중심 모드에서는 영상 API를 호출할 수 없습니다.')
        const selected=await selectedVideoModel(input.project.employee_email,input.model_ref.id)
        if(selected.fingerprint!==input.model_ref.fingerprint)throw Error('제출 후 모델 설정이 변경되었습니다. 해당 작업은 보완이 필요합니다.')
        const plan=m.plans?.find((p:any)=>p.number===number)?.ai
        const source=m.ai_sources?.[String(number)]
        const options=input.motion.automation
        const all=m.plans?.filter((p:any)=>p.ai)||[]
        const total=input.scenes.at(-1).end
        if(!plan||!Number.isFinite(plan.duration)||plan.duration<1||plan.duration>options.max_ai_seconds||all.length>options.max_ai_clips||all.reduce((sum:number,p:any)=>sum+p.ai.duration,0)>total*.2+.001
            ||typeof plan.prompt!=='string'||plan.prompt.length>4000||!source?.path?.startsWith(`std-motion/${job.id}/sources/`))throw Error('검수한 짧은 영상 구간과 원본이 필요합니다.')
        const patch=async(changes:any)=>{const r=await db.rpc('patch_std_motion_job',{p_job_id:job.id,p_token:body.worker_token,p_patch:changes});if(r.error)throw r.error;return r.data}
        let entry=m.provider_requests?.[String(number)]
        const planFingerprint=createHash('sha256').update(JSON.stringify(plan)).digest('hex')
        if(entry&&entry.plan_fingerprint!==planFingerprint)throw Error('기존 영상 생성 요청의 연출이 변경되었습니다. 접수 여부 확인이 필요합니다.')
        if(!entry) {
            if(body.action!=='create')throw Error('생성 요청을 먼저 등록해 주세요.')
            entry={state:'creating',plan_fingerprint:planFingerprint,started_at:new Date().toISOString()}
            // Commit intent BEFORE paid POST. An ambiguous connection never starts a second paid request.
            const reserved=await db.from('std_project_assets').update({metadata:{...m,provider_requests:{...m.provider_requests,[number]:entry}},updated_at:new Date().toISOString()})
                .eq('id',job.id).eq('updated_at',job.updated_at).eq('metadata->>worker_token',body.worker_token).select('id').maybeSingle()
            if(reserved.error||!reserved.data)return NextResponse.json({state:'retry_before_create'},{status:409})
            try {
                const image=await createGcsSignedReadUrl({bucket:source.bucket,objectPath:source.path,expiresInMinutes:60})
                const request=await createProviderVideo(selected.config,selected.secret,plan,image)
                entry={state:'submitted',plan_fingerprint:planFingerprint,...request}
                await patch({provider_requests:{...m.provider_requests,[number]:entry}})
            } catch {
                await patch({provider_requests:{...m.provider_requests,[number]:{...entry,state:'needs_reconcile'}}})
                throw Error('생성 요청의 접수 여부를 확인해야 합니다. 중복 결제를 피하기 위해 자동 재요청하지 않습니다.')
            }
            return NextResponse.json({state:'pending'})
        }
        if(!entry.id)throw Error('기존 생성 요청의 접수 여부 확인이 필요합니다. 자동 재요청하지 않습니다.')
        const status=await pollProviderVideo(selected.config,selected.secret,entry)
        return NextResponse.json(status)
    } catch(error:any) { return NextResponse.json({error:error.message||'영상 생성 연결 오류'},{status:409}) }
}
