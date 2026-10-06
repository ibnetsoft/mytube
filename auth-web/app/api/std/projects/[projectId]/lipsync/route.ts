import { NextResponse } from 'next/server'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { isComicProject } from '@/lib/stdComic'
import { lipSyncPlan } from '@/lib/stdLipSync'

export const dynamic = 'force-dynamic'

async function bundle(req: Request, id: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const p = await db.from('std_projects').select('*').eq('id', id).eq('employee_email', auth.requester.email).maybeSingle()
    if (p.error) throw p.error
    if (!p.data) return { response: NextResponse.json({ error: 'Project not found' }, { status: 404 }) }
    const [s, a] = await Promise.all([
        db.from('std_project_scenes').select('*').eq('project_id', id).order('scene_number'),
        db.from('std_project_assets').select('*').eq('project_id', id).order('created_at', { ascending: false }),
    ])
    if (s.error || a.error) throw s.error || a.error
    return { project: p.data, scenes: s.data || [], assets: a.data || [] }
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const b = await bundle(req, params.projectId)
        if (b.response) return b.response
        let plan: any[] = [], preparationError = ''
        try { plan = lipSyncPlan(b.project, b.scenes!, b.assets!) } catch (e: any) { preparationError = e.message }
        const key = await db.from('global_settings').select('value').eq('key', 'sys_api_hedra').maybeSingle()
        if (key.error) throw key.error
        return NextResponse.json({ configured: Boolean(key.data?.value || process.env.HEDRA_API_KEY), preparationError,
            scenes: plan.map(p => {
                const job = b.assets!.find(a => a.metadata?.kind === 'lipsync_job' && a.metadata?.fingerprint === p.fingerprint)
                const scene = b.scenes!.find(s => Number(s.scene_number) === p.scene_number)
                const source = b.project.project_payload?.structure?.scenes?.find((s: any) => Number(s.scene_number) === p.scene_number)
                const m = source?.metadata || scene?.metadata || {}
                const ae = [m.ae_effect_asset, m.ae_motion_asset].find(a => a?.lipsync_fingerprint === p.fingerprint && a?.gcs_path)
                return { number: p.scene_number, fingerprint: p.fingerprint, speakers: [...new Set(p.shots.map((s: any) => s.speaker))],
                    imageUrl: p.image ? `/api/std/projects/${params.projectId}/assets/file?assetId=${p.image.id}` : '',
                    status: job?.metadata?.state || 'not_started', error: job?.metadata?.error || '',
                    videoUrl: job?.metadata?.output_asset_id ? `/api/std/projects/${params.projectId}/assets/file?assetId=${job.metadata.output_asset_id}` : '',
                    aeUrl: ae?.media_url || '', aeState: job?.metadata?.ae_state || '', aeReviewed: Boolean(job?.metadata?.ae_reviewed), aeDirection: JSON.stringify(source?.ae_motion_plan?.enabled ? source.ae_motion_plan : { camera: 'slow_push_in', motion: { push: .015, shake: 0 }, vfx: [], purpose: '대사 표정과 입모양을 유지하는 약한 화면 확대' }, null, 2), points: job?.metadata?.points || {} }
            }) })
    } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 400 }) }
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const b = await bundle(req, params.projectId)
        if (b.response) return b.response
        const body = await req.json()
        if (isComicProject(b.project)) throw new Error('대사 립싱크는 일반 영상 모드에서 지원합니다.')
        const p = lipSyncPlan(b.project, b.scenes!, b.assets!).find(s => s.scene_number === Number(body.scene_number))
        if (!p?.image || p.end <= p.start) throw new Error('대사와 인물 이미지가 있는 씬을 선택해 주세요.')
        if (body.fingerprint !== p.fingerprint) throw new Error('음성 또는 이미지가 변경되었습니다. 최신 씬을 다시 확인해 주세요.')
        const job = b.assets!.find(a => a.metadata?.kind === 'lipsync_job' && a.metadata?.fingerprint === p.fingerprint)
        if (body.action === 'generate' || body.action === 'retry') {
            const k = await db.from('global_settings').select('value').eq('key', 'sys_api_hedra').maybeSingle()
            if (k.error) throw k.error
            if (!(k.data?.value || process.env.HEDRA_API_KEY)) throw new Error('관리자 API 설정에 Hedra 키를 등록해 주세요.')
            const points = body.points || {}
            for (const s of p.shots) {
                const xy = points[s.speaker]
                if (!Array.isArray(xy) || xy.length !== 2 || xy.some((n: any) => typeof n !== 'number' || !Number.isFinite(n) || n < 0 || n > 1)) throw new Error(`${s.speaker}: 이미지에서 말할 인물의 얼굴을 지정해 주세요.`)
                if (s.end - s.start < .5 || s.end - s.start > 600) throw new Error('대사 음성은 0.5~600초여야 합니다. 너무 짧은 대사는 자막에서 합쳐 주세요.')
            }
            if (body.action === 'retry' && job?.metadata?.state !== 'failed') throw new Error('실패한 생성 요청만 재시도할 수 있습니다.')
            if (job && body.action !== 'retry') return NextResponse.json({ success: true, message: '이 음성의 작업이 이미 등록되어 있습니다.', job })
            const result = await db.from('std_projects').update({ project_payload: { ...b.project.project_payload, lipsync: { enabled: true, provider: 'hedra' } }, updated_at: new Date().toISOString() })
                .eq('id', params.projectId).eq('updated_at', b.project.updated_at).select('id')
            if (result.error || !result.data?.length) throw new Error('프로젝트가 변경되었습니다. 새로고침 후 다시 시도해 주세요.')
            // Unique object path acts as an atomic generation claim across concurrent requests.
            const claimPath = `std/${params.projectId}/lipsync/${p.fingerprint}${body.action === 'retry' ? '-' + job!.id : ''}.json`
            const claim = await db.storage.from('content-assets').upload(claimPath, Buffer.from('{}'), { contentType: 'application/json', upsert: false })
            if (claim.error) throw new Error('이 씬의 요청이 이미 등록되었거나 저장을 확인할 수 없습니다. 새로고침해 주세요.')
            const inserted = await db.from('std_project_assets').insert({ project_id: params.projectId, scene_number: p.scene_number,
                asset_type: 'other', file_name: `lipsync_${p.scene_number}.json`, mime_type: 'application/json', status: 'assigned',
                metadata: { kind: 'lipsync_job', state: 'queued', fingerprint: p.fingerprint, points, plan: p } }).select('*').single()
            if (inserted.error) { await db.storage.from('content-assets').remove([claimPath]); throw inserted.error }
            return NextResponse.json({ success: true, job: inserted.data })
        }
        if (!job || !['review_pending', 'reviewed'].includes(job.metadata.state)) throw new Error('완료된 대사 영상을 먼저 확인해 주세요.')
        const row = b.scenes!.find(s => Number(s.scene_number) === p.scene_number)!
        const payload = b.project.project_payload || {}
        if (body.action === 'review_lipsync') {
            const output = b.assets!.find(a => a.id === job.metadata.output_asset_id)
            if (!output) throw new Error('대사 영상 파일이 없습니다.')
            const ref = { ...output.metadata, status: 'ready', lipsync_reviewed: true, asset_id: output.id }
            const patch = (s: any) => {
                if (Number(s.scene_number) !== p.scene_number) return s
                const meta = { ...(s.metadata || {}), lipsync_asset: ref }
                // Existing AE output belongs to the earlier source and cannot be reused.
                delete meta.ae_motion_asset; delete meta.ae_effect_asset
                return { ...s, video_generation_mode: 'lipsync', ae_motion_status: 'planned', ae_effect_status: 'not_required', ae_motion_video_url: null, ae_video_url: null, metadata: meta, duration_seconds: p.end - p.start,
                    ae_motion_plan: { preset: 'subtle_dialogue', mood: 'natural', camera: 'slow_push_in', light: 'preserve', vfx: [], intensity: .25, motion: { push: .015, drift_x: 0, drift_y: 0, shake: 0 }, ...(s.ae_motion_plan || {}), enabled: true, input_source: 'lipsync_asset', duration_seconds: p.end - p.start, timing_locked: true },
                    ae_effect_plan: { enabled: false, reason: 'lipsync_uses_motion_postprocess' } }
            }
            const update = await db.from('std_projects').update({ project_payload: { ...payload, ae_scene_delivery: 'gcs',
                structure: { ...payload.structure, ae_scene_delivery: 'gcs', scenes: (payload.structure?.scenes || []).map(patch) } }, updated_at: new Date().toISOString() })
                .eq('id', params.projectId).eq('updated_at', b.project.updated_at).select('id')
            if (update.error || !update.data?.length) throw new Error('프로젝트가 변경되었습니다. 다시 시도해 주세요.')
            const sr = await db.from('std_project_scenes').update({ metadata: patch({ ...row, ae_motion_plan: payload.structure?.scenes?.find((s: any) => Number(s.scene_number) === p.scene_number)?.ae_motion_plan }).metadata, updated_at: new Date().toISOString() }).eq('id', row.id)
            if (sr.error) throw sr.error
        } else if (body.action === 'review_ae') {
            const source = payload.structure?.scenes?.find((s: any) => Number(s.scene_number) === p.scene_number)
            const ae = [source?.metadata?.ae_motion_asset, source?.metadata?.ae_effect_asset].find(a => a?.lipsync_fingerprint === p.fingerprint && a?.status === 'ready' && a?.gcs_path)
            if (!ae || Math.abs(Number(ae.duration_seconds) - (p.end - p.start)) > .12) throw new Error('현재 립싱크 영상으로 만든 AE 결과가 필요합니다.')
            const inserted = await db.from('std_project_assets').insert({ project_id: params.projectId, scene_id: row.id, scene_number: p.scene_number,
                asset_type: 'video', file_name: `scene_${p.scene_number}_lipsync_ae.mp4`, mime_type: 'video/mp4', status: 'assigned',
                metadata: { ...ae, storage_provider: 'gcs', lipsync_reviewed: true, ae_reviewed: true, timing_locked: true } })
            if (inserted.error) throw inserted.error
        } else throw new Error('Invalid action')
        const done = await db.from('std_project_assets').update({ metadata: { ...job.metadata, state: 'reviewed', ...(body.action === 'review_ae' ? { ae_reviewed: true } : {}) }, updated_at: new Date().toISOString() }).eq('id', job.id)
        if (done.error) throw done.error
        return NextResponse.json({ success: true })
    } catch (e: any) { return NextResponse.json({ error: e.message }, { status: 400 }) }
}
