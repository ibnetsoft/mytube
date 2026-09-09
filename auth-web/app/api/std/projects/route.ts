import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { data, error } = await supabaseAdmin
        .from('std_projects')
        .select('id,title,status,language,employee_email,topic_queue_id,assigned_duration_minutes,estimated_payout,drive_folder_id,created_at,updated_at,submitted_at,progress_payload')
        .eq('employee_email', auth.requester.email)
        .order('updated_at', { ascending: false })

    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    const projects = data || []
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
            return {
                ...project,
                shared_submission: sharedSubmission && sharedSubmission.id !== project.id
                    ? { project_id: sharedSubmission.id, submitted_at: sharedSubmission.submitted_at }
                    : null,
            }
        }),
    })
}
