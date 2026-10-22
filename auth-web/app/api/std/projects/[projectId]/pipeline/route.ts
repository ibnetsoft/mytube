import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
export const dynamic = 'force-dynamic'

export async function GET(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    const project = await db.from('std_projects').select('id,pipeline_run_id:progress_payload->>pipeline_run_id').eq('id', params.projectId).eq('employee_email', auth.requester.email).maybeSingle()
    if (project.error) return NextResponse.json({ error: 'Project read failed' }, { status: 500 })
    if (!project.data) return NextResponse.json({ error: 'Project not found' }, { status: 404 })
    const id = project.data.pipeline_run_id
    if (!id) return NextResponse.json({ run: null })
    const run = await db.from('std_pipeline_runs').select('id,status,render_queue_id,warnings,updated_at').eq('id', id).eq('project_id', params.projectId).maybeSingle()
    if (run.error) return NextResponse.json({ error: 'Pipeline read failed' }, { status: 503 })
    if (!run.data) return NextResponse.json({ run: null, stages: [], render: null, status: 'missing_run', warning: '이전 제작 작업 기록을 찾지 못했습니다.' })
    const stages = await db.from('std_pipeline_stages').select('stage,scene_number,state,error,updated_at').eq('run_id', id)
    if (stages.error) return NextResponse.json({ error: 'Pipeline read failed' }, { status: 500 })
    const queue = run.data.render_queue_id ? await db.from('remote_render_queue').select('status,progress,message').eq('id', run.data.render_queue_id).maybeSingle() : { data: null, error: null }
    if (queue.error) return NextResponse.json({ error: 'Render status read failed' }, { status: 503 })
    return NextResponse.json({ run: run.data, stages: stages.data, render: queue.data })
}
