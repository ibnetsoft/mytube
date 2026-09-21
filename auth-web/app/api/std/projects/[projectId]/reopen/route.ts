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
