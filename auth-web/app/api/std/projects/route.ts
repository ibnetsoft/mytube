import { stdProjectListDisplay } from '@/lib/stdProjectListDisplay'
import { attachStdProjectCategories } from '@/lib/stdProjectCategories'
import { summarizeStdProject } from '@/lib/stdProjectStepStatus'
import { loadStdProjectStatusContext } from '@/lib/stdProjectStatusContext'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { protectCharacterReferenceUrls } from '@/lib/stdCharacterProtection'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { data, error } = await supabaseAdmin
        .from('std_projects')
        .select('id,title,status,language,category_id,employee_email,topic_queue_id,assigned_duration_minutes,estimated_payout,drive_folder_id,created_at,updated_at,submitted_at,saved_render_version:progress_payload->latest_render_version,saved_thumbnail_design_url:project_payload->thumbnail_design->>thumbnail_url')
        .eq('employee_email', auth.requester.email)
        .is('list_deleted_at', null)
        .order('updated_at', { ascending: false })

    if (error) return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    let projects: any[]
    try { projects = await attachStdProjectCategories(supabaseAdmin, data || []) }
    catch { return NextResponse.json({ success: false, error: 'Could not load project categories' }, { status: 503 }) }
    let contexts: any[] = []
    try { contexts = projects.length ? await loadStdProjectStatusContext(supabaseAdmin, projects.map(project => project.id)) : [] }
    catch (error: any) {
        console.error('[STD projects] status context unavailable:', error?.code, error?.message)
        return NextResponse.json({ error: 'Could not load project completion status' }, { status: 503 })
    }
    const contextById = new Map(contexts.map(context => [context.id, context]))
    if (projects.some(project => !contextById.has(project.id))) {
        return NextResponse.json({ success: false, error: 'Could not load project completion status' }, { status: 503 })
    }
    const assets: any[] = []
    const ids = projects.map(project => project.id)
    if (ids.length) {
        for (let offset = 0; ; offset += 1000) {
            const { data: batch, error: assetError } = await supabaseAdmin.from('std_project_assets')
                .select('id,project_id,scene_number,asset_type,status,drive_file_id,metadata,created_at')
                .in('project_id', ids).in('asset_type', ['image','video','audio','thumbnail'])
                .in('status', ['uploaded','assigned']).order('id').range(offset, offset + 999)
            if (assetError) return NextResponse.json({ success: false, error: 'Could not load project completion status' }, { status: 500 })
            assets.push(...(batch || []))
            if (!batch || batch.length < 1000) break
        }
    }
    const topicQueueIds = [...new Set(projects.map((project: any) => Number(project.topic_queue_id)).filter(Number.isFinite))]
    const { data: topicTitles, error: topicTitleError } = topicQueueIds.length
        ? await supabaseAdmin.from('topics_queue')
            .select('id,topic,generated_title,topic_en,topic_vi,topic_th,progress_title_translations:progress_payload->title_translations,structure_title_translations:pregenerated_structure->title_translations,metadata_title_translations:publish_metadata->title_translations')
            .in('id', topicQueueIds)
        : { data: [], error: null }
    if (topicTitleError) return NextResponse.json({ success: false, error: 'Could not load project titles' }, { status: 500 })
    const titleLocalizationByTopic = new Map((topicTitles || []).map((topic: any) => [Number(topic.id), {
        topic: topic.topic,
        generated_title: topic.generated_title,
        topic_en: topic.topic_en,
        topic_vi: topic.topic_vi,
        topic_th: topic.topic_th,
        title_translations: topic.progress_title_translations || topic.structure_title_translations || topic.metadata_title_translations || {},
    }]))
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
            const summary = project
            const context = contextById.get(project.id)
            return {
                ...summary,
                ...stdProjectListDisplay(project, context, assets.filter(asset => asset.project_id === project.id)),
                title_localization: titleLocalizationByTopic.get(Number(project.topic_queue_id)) || null,
                progress_payload: protectCharacterReferenceUrls(context?.progress_payload, project.id),
                step_status: summarizeStdProject(context || project, assets.filter(asset => asset.project_id === project.id)),
                shared_submission: sharedSubmission && sharedSubmission.id !== project.id
                    ? { project_id: sharedSubmission.id, submitted_at: sharedSubmission.submitted_at }
                    : null,
            }
        }),
    })
}

export async function DELETE(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    const body = await req.json().catch(() => null)
    const ids = body?.ids
    if (!Array.isArray(ids) || ids.length < 1 || ids.length > 100 || ids.some((id: unknown) => typeof id !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))) {
        return NextResponse.json({ success: false, error: '유효한 프로젝트를 선택해 주세요.' }, { status: 400 })
    }
    const uniqueIds = [...new Set(ids)] as string[]
    const { data, error } = await supabaseAdmin.from('std_projects').update({ list_deleted_at: new Date().toISOString() })
        .eq('employee_email', auth.requester.email).is('list_deleted_at', null).in('id', uniqueIds).select('id')
    if (error) return NextResponse.json({ success: false, error: '프로젝트를 삭제하지 못했습니다.' }, { status: 500 })
    return NextResponse.json({ success: true, deletedIds: (data || []).map(row => row.id) })
}
