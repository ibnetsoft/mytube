import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { getStdProjectRenderHistory } from '@/lib/stdRenderQueue'
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

    const latestVersion = Math.max(0, ...renderHistory.map(row => Number(row.render_version) || 0))
    const now = new Date().toISOString()
    const { data: updated, error: updateError } = await supabaseAdmin
        .from('std_projects')
        .update({
            status: 'in_progress',
            submitted_at: null,
            progress_payload: {
                ...(project.progress_payload || {}),
                latest_render_version: latestVersion,
                editing_render_version: latestVersion + 1,
                rerender_draft: true,
                reopened_from_status: project.status,
                reopened_for_rerender_at: now,
            },
            updated_at: now,
        })
        .eq('id', project.id)
        .eq('status', project.status)
        .select('*')
        .single()

    if (updateError) return NextResponse.json({ success: false, error: updateError.message }, { status: 500 })
    return NextResponse.json({
        success: true,
        project: updated,
        render_history: renderHistory,
        next_render_version: latestVersion + 1,
    })
}
