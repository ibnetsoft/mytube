import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { AI_SFX_SOURCE, sfxSnapshot, projectSfxCatalog, attachSfxAssets, mergeAiSfx, preserveSfxForAnalysis } from '@/lib/stdAiSfx'

export const dynamic = 'force-dynamic'

async function owned(req: Request, projectId: string) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return { response: auth.response }
    const { data, error } = await supabaseAdmin.from('std_projects').select('*')
        .eq('id', projectId).eq('employee_email', auth.requester.email).maybeSingle()
    if (error || !data) return { response: NextResponse.json({ error: '프로젝트를 찾지 못했습니다.' }, { status: 404 }) }
    return { project: data }
}
export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const access = await owned(req, params.projectId)
    if (access.response) return access.response
    const { data, error } = await supabaseAdmin.from('remote_hermes_queue')
        .select('id,status,error_message,result_payload').eq('job_type','sfx_plan_generate')
        .eq('payload->>project_id', params.projectId).order('created_at', { ascending: false }).limit(1).maybeSingle()
    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ job: data })
}
export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const access = await owned(req, params.projectId)
    if (access.response) return access.response
    const project = access.project
    if (project.submitted_at || ['approved','canceled','review_requested'].includes(project.status))
        return NextResponse.json({ error: '편집 가능한 프로젝트에서 효과음을 구성해 주세요.' }, { status: 409 })
    try {
        const body = await req.json()
        const payload = project.project_payload || {}
        const subtitles = payload.subtitles || []
        if (!subtitles.length) throw new Error('먼저 자막을 저장해 주세요.')
        const snapshot = sfxSnapshot(subtitles)
        if (!Array.isArray(body.subtitles) || sfxSnapshot(body.subtitles) !== snapshot)
            return NextResponse.json({ error: '화면의 자막이 아직 저장되지 않았습니다. 저장 후 다시 시도해 주세요.' }, { status: 409 })
        const settings = payload.render_settings || {}
        const existing = settings.sfx_cues || []
        if (body.action === 'apply') {
            const found = await supabaseAdmin.from('remote_hermes_queue').select('*').eq('id', body.job_id)
                .eq('job_type','sfx_plan_generate').eq('payload->>project_id', project.id).eq('status','completed').maybeSingle()
            if (found.error || !found.data) throw new Error('완료된 효과음 구성이 없습니다.')
            const job = found.data
            if (job.payload.snapshot !== snapshot || job.result_payload?.snapshot !== snapshot)
                return NextResponse.json({ error: '분석 중 자막이 변경되었습니다. 다시 구성해 주세요.' }, { status: 409 })
            if (settings.sfx_plan?.job_id === job.id) return NextResponse.json({ success: true })
            const proposed = (job.result_payload?.cues || []).filter((c: any) => c.source === AI_SFX_SOURCE
                && Number.isInteger(c.subtitle_index) && subtitles[c.subtitle_index]?.text === c.subtitle_text
                && Number.isInteger(c.word_boundary) && c.word_boundary >= 0
                && c.word_boundary <= String(c.subtitle_text).trim().split(/\s+/).length
                && String(c.scene_number) === String(subtitles[c.subtitle_index]?.scene_number)
                && c.volume_db >= -30 && c.volume_db <= -16 && c.duration >= .2 && c.duration <= 8)
            const cues = await attachSfxAssets(project.id, proposed, job.payload.catalog || [])
            const next = { ...payload, render_settings: { ...settings,
                sfx_cues: mergeAiSfx(existing, cues, subtitles), sfx_plan: { job_id: job.id, snapshot, status: 'ready' } } }
            const saved = await supabaseAdmin.from('std_projects').update({ project_payload: next, updated_at: new Date().toISOString() })
                .eq('id', project.id).eq('updated_at', project.updated_at).select('id')
            if (saved.error || !saved.data?.length) throw new Error('프로젝트가 변경되었습니다. 다시 적용해 주세요.')
            return NextResponse.json({ success: true, count: cues.length })
        }
        const pending = await supabaseAdmin.from('remote_hermes_queue').select('id,status').eq('job_type','sfx_plan_generate')
            .eq('payload->>project_id', project.id).in('status',['pending','claimed','rendering','running'])
            .order('created_at',{ascending:false}).limit(1).maybeSingle()
        if (pending.error) throw pending.error
        if (pending.data) return NextResponse.json({ job: pending.data })
        const catalog = await projectSfxCatalog(project.id)
        if (!catalog.length) throw new Error('사용 가능한 효과음이 없습니다.')
        const inserted = await supabaseAdmin.from('remote_hermes_queue').insert({
            job_type: 'sfx_plan_generate', status: 'pending', priority: 10,
            payload: { project_id: project.id, snapshot, catalog, existing_cues: preserveSfxForAnalysis(existing, subtitles),
                units: subtitles.map((s: any) => ({ id: s.id, text: s.text, scene_number: s.scene_number, anchor_scope: 'subtitle' })) },
        }).select('id,status').single()
        if (inserted.error) throw inserted.error
        return NextResponse.json({ job: inserted.data })
    } catch (e: any) { return NextResponse.json({ error: e.message || '효과음 구성에 실패했습니다.' }, { status: 500 }) }
}
