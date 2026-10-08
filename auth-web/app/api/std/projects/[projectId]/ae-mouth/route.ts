import { NextResponse } from 'next/server'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { aeMouthApplicable, aeMouthInput, currentAeMouthJob } from '@/lib/stdAeMouth'
import { ensureAeMouthJob } from '@/lib/stdAeMouthQueue'

export const dynamic = 'force-dynamic'

async function bundle(req: Request, id: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const project = await db.from('std_projects').select('*').eq('id', id).eq('employee_email', auth.requester.email).maybeSingle()
    if (project.error) throw project.error
    if (!project.data) return { response: NextResponse.json({ error: 'Project not found' }, { status: 404 }) }
    const [s, a] = await Promise.all([
        db.from('std_project_scenes').select('*').eq('project_id', id).order('scene_number'),
        db.from('std_project_assets').select('*').eq('project_id', id).order('created_at', { ascending: false }),
    ])
    if (s.error || a.error) throw s.error || a.error
    return { project: project.data, scenes: s.data || [], assets: a.data || [] }
}

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const b = await bundle(req, params.projectId)
        if (b.response) return b.response
        if (!aeMouthApplicable(b.project, b.scenes!)) return NextResponse.json({ applicable: false })
        let job: any, error = ''
        try { job = currentAeMouthJob(b.project, b.scenes!, b.assets!) } catch (e: any) { error = e.message }
        return NextResponse.json({ applicable: true, preparationError: error, fingerprint: job?.metadata?.fingerprint || '',
            status: job?.metadata?.state || 'not_started', error: job?.metadata?.error || '',
            results: (job?.metadata?.results || []).map((r: any) => ({ number: r.number, status: r.status, reason: r.reason || '',
                speakers: r.speakers || [], direction: r.direction || '',
                videoUrl: r.asset_id ? `/api/std/projects/${params.projectId}/assets/file?assetId=${r.asset_id}` : '',
            })),
        })
    } catch (e: any) { return NextResponse.json({ error: e.message || 'AE 작업 조회 실패' }, { status: 400 }) }
}

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    try {
        const b = await bundle(req, params.projectId)
        if (b.response) return b.response
        const body = await req.json()
        const { fingerprint } = aeMouthInput(b.project, b.scenes!, b.assets!)
        const job = currentAeMouthJob(b.project, b.scenes!, b.assets!)
        if (body.fingerprint !== (job?.metadata?.fingerprint || fingerprint)) throw new Error('음성·이미지·대본이 변경되었습니다. 작업 목록을 새로 확인해 주세요.')
        if (!job) throw new Error('제출 버튼으로 AE 후작업을 먼저 요청해 주세요.')
        if (body.action === 'retry') {
            await ensureAeMouthJob(b.project, b.scenes!, b.assets!, true)
            return NextResponse.json({ success: true })
        }
        if (body.action === 'approve_direction') {
            if (job.metadata.state !== 'direction_pending' || !job.metadata.results.some((r: any) => r.status === 'direction_pending')) throw new Error('승인할 준비가 된 씬의 AE 지침이 없습니다.')
            const results = job.metadata.results.map((r: any) => r.status === 'direction_pending' ? { ...r, status: 'direction_approved' } : r)
            const updated = await db.from('std_project_assets').update({ metadata: { ...job.metadata, results, state: 'direction_approved', phase: 'render' }, updated_at: new Date().toISOString() })
                .eq('id', job.id).eq('updated_at', job.updated_at).select('id').maybeSingle()
            if (updated.error || !updated.data) throw new Error('작업 상태가 변경되었습니다. 다시 확인해 주세요.')
            return NextResponse.json({ success: true })
        }
        if (!['review', 'exclude'].includes(body.action) || !['direction_pending', 'review_pending', 'reviewed'].includes(job.metadata.state)) throw new Error('검수할 수 없는 작업입니다.')
        const row = job.metadata.results?.find((r: any) => r.number === Number(body.number))
        if (!row) throw new Error('해당 씬을 찾을 수 없습니다.')
        if (body.action === 'review') {
            if (!['review_pending', 'approved'].includes(row.status) || !row.asset_id) throw new Error('완성된 AE 영상만 승인할 수 있습니다.')
            const asset = b.assets!.find(a => a.id === row.asset_id && a.asset_type === 'video'
                && Number(a.scene_number) === row.number && a.metadata?.ae_mouth_fingerprint === job.metadata.fingerprint && a.metadata?.timing_locked
                && a.metadata?.render_sha256 === row.render_sha256 && Math.abs(Number(a.metadata.duration_seconds) - Number(row.duration)) <= .12)
            if (!asset) throw new Error('검수 영상이 현재 작업과 일치하지 않습니다.')
            const approved = await db.from('std_project_assets').update({ metadata: { ...asset.metadata, ae_reviewed: true } }).eq('id', asset.id).eq('project_id', params.projectId)
            if (approved.error) throw approved.error
        } else {
            if (row.status !== 'needs_review' || String(body.reason || '').trim().length < 5) throw new Error('화자 판별을 보류한 씬에 한해 제외 사유를 적어 주세요.')
        }
        const results = job.metadata.results.map((r: any) => r.number !== row.number ? r : body.action === 'review'
            ? { ...r, status: 'approved' } : { ...r, status: 'skipped', reason: String(body.reason).trim(), excluded_by_user: true })
        const state = results.every((r: any) => ['approved', 'skipped'].includes(r.status)) ? 'reviewed'
            : results.some((r: any) => r.status === 'direction_pending') ? 'direction_pending' : 'review_pending'
        const updated = await db.from('std_project_assets').update({ metadata: { ...job.metadata, results, state }, updated_at: new Date().toISOString() })
            .eq('id', job.id).eq('updated_at', job.updated_at).select('id').maybeSingle()
        if (updated.error || !updated.data) throw new Error('다른 검수가 저장되었습니다. 새로 확인해 주세요.')
        return NextResponse.json({ success: true, state })
    } catch (e: any) { return NextResponse.json({ error: e.message || 'AE 검수 실패' }, { status: 409 }) }
}
