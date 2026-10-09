import { loadStdProjectAssets } from '@/lib/stdProjectAssets'
import { aeMouthApplicable } from '@/lib/stdAeMouth'
import { ensureAeMouthJob } from '@/lib/stdAeMouthQueue'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { enqueueStdProjectRender, getStdProjectRenderHistory } from '@/lib/stdRenderQueue'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export async function POST(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { data: project, error: projectError } = await supabaseAdmin
        .from('std_projects')
        .select('*')
        .eq('id', params.projectId)
        .eq('employee_email', auth.requester.email)
        .maybeSingle()

    if (projectError) return NextResponse.json({ success: false, error: projectError.message }, { status: 500 })
    if (!project) return NextResponse.json({ success: false, error: 'Project not found' }, { status: 404 })

    let renderHistory: any[]
    try {
        renderHistory = await getStdProjectRenderHistory(project.id)
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'Could not load render history' }, { status: 500 })
    }

    const activeRender = renderHistory.find(row => ['pending', 'rendering'].includes(String(row?.status || '')))
    if (activeRender) {
        return NextResponse.json({
            success: false,
            error: '현재 렌더링 작업이 대기 또는 진행 중입니다. 완료 후 다시 수정할 수 있습니다.',
            render_queue_id: activeRender.id,
        }, { status: 409 })
    }

    // Accept submission while Codex/AE postprocessing runs; enqueue only reviewed outputs.
    try {
        const [scenes, assets] = await Promise.all([
            supabaseAdmin.from('std_project_scenes').select('*').eq('project_id', project.id).order('scene_number'),
            loadStdProjectAssets(supabaseAdmin, project.id, '*'),
        ])
        if (scenes.error || assets.error) throw scenes.error || assets.error
        if (aeMouthApplicable(project, scenes.data || [])) {
            const pending = await ensureAeMouthJob(project, scenes.data || [], assets.data || [])
            if (!project.project_payload?.ae_mouth?.enabled) {
                const enabled = await supabaseAdmin.from('std_projects').update({
                    project_payload: { ...project.project_payload, ae_mouth: { enabled: true, first_scene: 19 } },
                    updated_at: new Date().toISOString(),
                }).eq('id', project.id).eq('updated_at', project.updated_at).select('id').maybeSingle()
                if (enabled.error || !enabled.data) throw new Error('프로젝트가 변경되었습니다. 다시 제출해 주세요.')
            }
            if (!pending.ready) return NextResponse.json({ success: true, postprocess_pending: true,
                ae_job_id: pending.job?.id || null, message: '제출 완료. AE 후작업과 검수 후 최종 렌더링이 자동으로 진행됩니다.' }, { status: 202 })
        }
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'AE 작업 등록 실패' }, { status: 409 })
    }

    let renderQueueRow: any
    try {
        renderQueueRow = await enqueueStdProjectRender(project.id)
    } catch (error: any) {
        return NextResponse.json({ success: false, error: error?.message || 'Could not enqueue rerender' }, { status: 500 })
    }

    const renderVersion = Number(renderQueueRow?.metadata?.render_version || renderQueueRow?.render_version || 1)
    return NextResponse.json({
        success: true,
        project,
        render_history: renderHistory,
        render_queue: renderQueueRow,
        next_render_version: renderVersion,
    })
}
