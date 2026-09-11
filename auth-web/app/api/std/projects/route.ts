import { summarizeStdProject } from '@/lib/stdProjectStepStatus'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { data, error } = await supabaseAdmin
        .from('std_projects')
        .select('id,title,status,language,employee_email,topic_queue_id,assigned_duration_minutes,estimated_payout,drive_folder_id,created_at,updated_at,submitted_at,progress_payload,project_payload')
        .eq('employee_email', auth.requester.email)
        .order('updated_at', { ascending: false })

    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    const projects = data || []
    const assets: any[] = []
    const ids = projects.map(project => project.id)
    if (ids.length) {
        for (let offset = 0; ; offset += 1000) {
            const { data: batch, error: assetError } = await supabaseAdmin.from('std_project_assets')
                .select('project_id,scene_number,asset_type,status,drive_file_id')
                .in('project_id', ids).in('asset_type', ['image','video','audio','thumbnail'])
                .in('status', ['uploaded','assigned']).order('id').range(offset, offset + 999)
            if (assetError) return NextResponse.json({ success: false, error: 'Could not load project completion status' }, { status: 500 })
            assets.push(...(batch || []))
            if (!batch || batch.length < 1000) break
        }
    }
    const topicQueueIds = [...new Set(projects.map((project: any) => Number(project.topic_queue_id)).filter(Number.isFinite))]
    let sharedSubmissions: any[] = []
    if (topicQueueIds.length > 0) {
        const { data: submittedProjects, error: submittedProjectsError } = await supabaseAdmin
            .from('std_projects')
            .select('id,topic_queue_id,submitted_at,updated_at')
            .in('topic_queue_id', topicQueueIds)
            .not('submitted_at', 'is', null)
            .order('submitted_at', { ascending: false })
        if (submittedProjectsError) return NextResponse.json({ success: false, error: submittedProjectsError.message }, { status: 500 })
        sharedSubmissions = submittedProjects || []
    }
    const submissionByTopic = new Map<number, any>()
    sharedSubmissions.forEach((submission: any) => {
        const topicQueueId = Number(submission.topic_queue_id)
        if (Number.isFinite(topicQueueId) && !submissionByTopic.has(topicQueueId)) {
            submissionByTopic.set(topicQueueId, submission)
        }
    })
    return NextResponse.json({
        success: true,
        projects: projects.map((project: any) => {
            const sharedSubmission = submissionByTopic.get(Number(project.topic_queue_id))
            const { project_payload, ...summary } = project
            return {
                ...summary,
                step_status: summarizeStdProject(project, assets.filter(asset => asset.project_id === project.id)),
                shared_submission: sharedSubmission && sharedSubmission.id !== project.id
                    ? { project_id: sharedSubmission.id, submitted_at: sharedSubmission.submitted_at }
                    : null,
            }
        }),
    })
}
