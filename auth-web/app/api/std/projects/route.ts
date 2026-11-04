import { stdProjectListDisplay } from '@/lib/stdProjectListDisplay'
import { attachStdProjectCategories } from '@/lib/stdProjectCategories'
import { summarizeStdProject } from '@/lib/stdProjectStepStatus'
import { loadStdProjectListStatusContext } from '@/lib/stdProjectStatusContext'
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireStdUser } from '@/lib/stdWeb'
import { protectCharacterReferenceUrls } from '@/lib/stdCharacterProtection'
import { getServerCache, setServerCache } from '@/lib/server-cache'
import { createHash } from 'crypto'

export const dynamic = 'force-dynamic'
const PROJECT_LIST_CACHE_SECONDS = 15
const inflightLists = new Map<string, Promise<any>>()

async function boundedCache<T>(operation: Promise<T>, fallback: T): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined
    try {
        return await Promise.race([operation, new Promise<T>(resolve => { timer = setTimeout(() => resolve(fallback), 400) })])
    } catch { return fallback }
    finally { if (timer) clearTimeout(timer) }
}

function projectListCacheKey(email: string, projects: any[]) {
    const digest = createHash('sha256').update(JSON.stringify([email.toLowerCase(), projects])).digest('hex')
    return `std-project-list:v1:${digest}`
}

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
    const baseProjects = data || []
    const cacheKey = projectListCacheKey(auth.requester.email, baseProjects)
    const forceRefresh = req.headers.get('x-std-list-refresh') === '1'
    if (!forceRefresh) {
        const cached = await boundedCache(getServerCache<any>(cacheKey), null)
        if (cached?.success === true && Array.isArray(cached.projects)) return NextResponse.json(cached, { headers: { 'X-Std-List-Cache': 'hit' } })
        const pending = inflightLists.get(cacheKey)
        if (pending) {
            try { return NextResponse.json(await pending, { headers: { 'X-Std-List-Cache': 'shared' } }) } catch { /* retry fresh */ }
        }
    }
    const build = buildProjectList(baseProjects)
    if (!forceRefresh) inflightLists.set(cacheKey, build)
    try {
        const result = await build
        await boundedCache(setServerCache(cacheKey, result, PROJECT_LIST_CACHE_SECONDS), undefined)
        return NextResponse.json(result, { headers: { 'X-Std-List-Cache': 'miss' } })
    } catch (error: any) {
        console.error('[STD projects] list data unavailable:', error?.code, error?.message)
        return NextResponse.json({ success: false, error: 'Could not load project completion status' }, { status: 503 })
    } finally {
        if (inflightLists.get(cacheKey) === build) inflightLists.delete(cacheKey)
    }
}

async function buildProjectList(baseProjects: any[]) {
    const ids = baseProjects.map((project: any) => project.id)
    const topicQueueIds = [...new Set(baseProjects.map((project: any) => Number(project.topic_queue_id)).filter((id: number) => Number.isFinite(id) && id > 0))]
    // These independent reads used to run one after another on every modal open.
    const loadAssets = async () => {
        const assets: any[] = []
        if (!ids.length) return assets
        for (let offset = 0; ; offset += 1000) {
            const { data: batch, error } = await supabaseAdmin.from('std_project_assets')
                .select('id,project_id,scene_number,asset_type,status,created_at,gcs_path:metadata->>gcs_path,storage_path:metadata->>storage_path,gcs_signed_url:metadata->>gcs_signed_url,gcs_public_url:metadata->>gcs_public_url,script_sha256:metadata->content_identity->>script_sha256')
                .in('project_id', ids).in('asset_type', ['image','video','audio','thumbnail'])
                .in('status', ['uploaded','assigned']).order('id').range(offset, offset + 999)
            if (error) throw error
            assets.push(...(batch || []).map((asset: any) => ({ ...asset, metadata: {
                gcs_path: asset.gcs_path, storage_path: asset.storage_path,
                gcs_signed_url: asset.gcs_signed_url, gcs_public_url: asset.gcs_public_url,
                content_identity: { script_sha256: asset.script_sha256 },
            } })))
            if (!batch || batch.length < 1000) return assets
        }
    }
    let projects: any[], contexts: any[], assets: any[], topicTitles: any[], sharedSubmissions: any[]
    try {
        const [categories, statusContexts, projectAssets, titles, submissions] = await Promise.all([
            attachStdProjectCategories(supabaseAdmin, baseProjects),
            loadStdProjectListStatusContext(supabaseAdmin, ids),
            loadAssets(),
            topicQueueIds.length ? supabaseAdmin.from('topics_queue')
                .select('id,topic,generated_title,topic_en,topic_vi,topic_th,progress_title_translations:progress_payload->title_translations,structure_title_translations:pregenerated_structure->title_translations,metadata_title_translations:publish_metadata->title_translations')
                .in('id', topicQueueIds) : Promise.resolve({ data: [], error: null }),
            topicQueueIds.length ? supabaseAdmin.from('std_projects')
                .select('id,topic_queue_id,submitted_at,updated_at').in('topic_queue_id', topicQueueIds)
                .not('submitted_at', 'is', null).order('submitted_at', { ascending: false }) : Promise.resolve({ data: [], error: null }),
        ])
        if (titles.error || submissions.error) throw titles.error || submissions.error
        projects = categories
        contexts = statusContexts
        assets = projectAssets
        topicTitles = titles.data || []
        sharedSubmissions = submissions.data || []
    } catch (error: any) {
        console.error('[STD projects] list data unavailable:', error?.code, error?.message)
        throw error
    }
    const contextById = new Map(contexts.map(context => [context.id, context]))
    if (projects.some(project => !contextById.has(project.id))) {
        throw new Error('Missing project status context')
    }
    const assetsByProject = new Map<string, any[]>()
    for (const asset of assets) {
        const group = assetsByProject.get(asset.project_id) || []
        group.push(asset)
        assetsByProject.set(asset.project_id, group)
    }
    const titleLocalizationByTopic = new Map((topicTitles || []).map((topic: any) => [Number(topic.id), {
        topic: topic.topic,
        generated_title: topic.generated_title,
        topic_en: topic.topic_en,
        topic_vi: topic.topic_vi,
        topic_th: topic.topic_th,
        title_translations: { ...topic.metadata_title_translations, ...topic.structure_title_translations, ...topic.progress_title_translations },
    }]))
    const submissionByTopic = new Map<number, any>()
    sharedSubmissions.forEach((submission: any) => {
        const topicQueueId = Number(submission.topic_queue_id)
        if (Number.isFinite(topicQueueId) && !submissionByTopic.has(topicQueueId)) {
            submissionByTopic.set(topicQueueId, submission)
        }
    })
    return {
        success: true,
        projects: projects.map((project: any) => {
            const sharedSubmission = submissionByTopic.get(Number(project.topic_queue_id))
            const summary = project
            const context = contextById.get(project.id)
            return {
                ...summary,
                ...stdProjectListDisplay(project, context, assetsByProject.get(project.id) || []),
                title_localization: titleLocalizationByTopic.get(Number(project.topic_queue_id)) || null,
                progress_payload: protectCharacterReferenceUrls(context?.progress_payload, project.id),
                step_status: summarizeStdProject(context || project, assetsByProject.get(project.id) || []),
                shared_submission: sharedSubmission && sharedSubmission.id !== project.id
                    ? { project_id: sharedSubmission.id, submitted_at: sharedSubmission.submitted_at }
                    : null,
            }
        }),
    }
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
