import { NextRequest, NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin, requireSuperAdmin } from '../_auth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

const CODEX_JOB_TYPE = 'codex_content_generate'
const REPAIR_JOB_TYPE = 'script_plan_generate'
const REPAIR_PIPELINE_JOB_TYPES = ['script_plan_generate', 'script_generate', 'publish_metadata_generate']
const ACTIVE_JOB_STATUSES = ['pending', 'claimed', 'rendering', 'running']

const asObject = (value: unknown): Record<string, any> => (
    value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : {}
)

const isAdminHidden = (topic: any): boolean => {
    const progress = asObject(topic?.progress_payload)
    return topic?.status === 'excluded' && (progress.admin_hidden === true || progress.admin_hidden === 'true')
}

function durationSeconds(topic: any): number {
    const minutes = Number(topic?.assigned_duration_minutes || topic?.recommended_duration_minutes || 5)
    return Math.max(60, Math.min(10_800, Math.round(minutes * 60)))
}

function topicPayload(topic: any, categoryName: string, requesterEmail: string) {
    const progress = asObject(topic.progress_payload)
    const structure = asObject(topic.pregenerated_structure)
    const title = String(topic.generated_title || progress.title_generation?.generated_title || topic.topic || '').trim()
    return {
        topic_queue_id: String(topic.id),
        topic: title,
        original_topic: String(topic.topic || '').trim(),
        upload_title: title,
        category: categoryName,
        category_name: categoryName,
        category_id: topic.category_id,
        language: String(topic.language || 'ko'),
        script_style: String(topic.assigned_script_style || 'story'),
        image_style: String(topic.assigned_image_style || structure.image_style || 'realistic'),
        target_duration_seconds: durationSeconds(topic),
        queued_from: 'codex_worker_admin_ui',
        queued_by: requesterEmail,
        queued_at: new Date().toISOString(),
    }
}

export async function GET(req: NextRequest) {
    const requester = await requireAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const [
            { data: categories, error: categoriesError },
            { data: topics, error: topicsError },
            { data: codexJobs, error: codexJobsError },
            { data: repairJobs, error: repairJobsError },
            { data: workers, error: workersError },
        ] = await Promise.all([
            supabaseAdmin.from('categories').select('id,name').limit(100),
            supabaseAdmin
                .from('topics_queue')
                .select('id,topic,generated_title,category_id,status,assigned_at,language,assigned_duration_minutes,recommended_duration_minutes,total_scenes,pregenerated_script_status,pregenerated_structure_status,pregenerated_structure,progress_payload,created_at')
                .order('created_at', { ascending: false })
                .limit(500),
            supabaseAdmin
                .from('remote_hermes_queue')
                .select('id,job_type,status,worker_status,progress,message,error_message,payload,worker_id,created_at,completed_at,attempt_number')
                .eq('job_type', CODEX_JOB_TYPE)
                .order('created_at', { ascending: false })
                .limit(100),
            supabaseAdmin
                .from('remote_hermes_queue')
                .select('id,job_type,status,worker_status,progress,message,error_message,payload,worker_id,created_at,completed_at,attempt_number')
                .in('job_type', REPAIR_PIPELINE_JOB_TYPES)
                .contains('payload', { repair_mode: true })
                .order('created_at', { ascending: false })
                .limit(100),
            supabaseAdmin.from('workers').select('worker_id,worker_group,last_heartbeat_at,allowed_job_types').order('registered_at', { ascending: false }),
        ])
        if (categoriesError) throw categoriesError
        if (topicsError) throw topicsError
        if (codexJobsError) throw codexJobsError
        if (repairJobsError) throw repairJobsError
        if (workersError) throw workersError

        const categoryNames = new Map((categories || []).map(category => [String(category.id), String(category.name || '')]))
        const now = Date.now()
        const workerRows = (workers || []).map(worker => ({
            ...worker,
            online: Boolean(worker.last_heartbeat_at) && now - new Date(worker.last_heartbeat_at).getTime() < 90_000,
            supports_codex: Array.isArray(worker.allowed_job_types) && worker.allowed_job_types.includes(CODEX_JOB_TYPE),
            supports_repair: Array.isArray(worker.allowed_job_types) && worker.allowed_job_types.includes(REPAIR_JOB_TYPE),
        }))
        const jobRows = [...(codexJobs || []), ...(repairJobs || [])]
            .sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
            .map(job => ({
            ...job,
            topic_queue_id: String(asObject(job.payload).topic_queue_id || ''),
            repair_mode: asObject(job.payload).repair_mode === true,
            flow: job.job_type === CODEX_JOB_TYPE ? 'new_generation' : 'repair',
        }))
        const latestJobByTopic = new Map<string, any>()
        for (const job of jobRows) {
            if (job.topic_queue_id && !latestJobByTopic.has(job.topic_queue_id)) latestJobByTopic.set(job.topic_queue_id, job)
        }
        const topicRows = (topics || []).map(topic => {
            const structure = asObject(topic.pregenerated_structure)
            const scenes = Array.isArray(structure.scenes) ? structure.scenes : []
            const progress = asObject(topic.progress_payload)
            return {
                id: String(topic.id),
                title: String(topic.generated_title || topic.topic || ''),
                generated_title: String(topic.generated_title || ''),
                category_id: topic.category_id,
                category_name: categoryNames.get(String(topic.category_id)) || `카테고리 ${topic.category_id}`,
                status: topic.status,
                language: topic.language || 'ko',
                duration_minutes: Number(topic.assigned_duration_minutes || topic.recommended_duration_minutes || 0),
                assigned_at: topic.assigned_at || null,
                script_status: topic.pregenerated_script_status || progress.pregenerated_script_status || 'not_ready',
                structure_status: topic.pregenerated_structure_status || progress.pregenerated_structure_status || 'not_ready',
                scene_count: scenes.length || Number(topic.total_scenes || structure.scene_count || 0),
                image_count: scenes.filter((scene: any) => Boolean(scene?.image_url)).length,
                thumbnail_status: progress.thumbnail_generation_status || (progress.thumbnail_bg_url ? 'completed' : 'not_started'),
                thumbnail_url: progress.thumbnail_bg_url || '',
                worker_id: '',
                latest_job: latestJobByTopic.get(String(topic.id)) || null,
                repair_status: String(progress.repair_status || ''),
                admin_hidden: isAdminHidden(topic),
                created_at: topic.created_at,
            }
        })
        const activeJobs = jobRows.filter(job => ACTIVE_JOB_STATUSES.includes(String(job.status || '').toLowerCase()))
        const visibleUserTopics = topicRows.filter(topic => (
            topic.status === 'pending'
            && !topic.assigned_at
            && Boolean(topic.generated_title.trim())
        ))
        const repairTopics = topicRows.filter(topic => topic.admin_hidden)
        const newGenerationTopics = topicRows.filter(topic => !topic.admin_hidden)

        return NextResponse.json({
            generated_at: new Date().toISOString(),
            summary: {
                total_topics: topicRows.length,
                prepared_topics: topicRows.filter(topic => topic.script_status === 'ready').length,
                active_jobs: activeJobs.length,
                failed_jobs: jobRows.filter(job => ['failed', 'error'].includes(String(job.status || '').toLowerCase())).length,
                thumbnails_completed: topicRows.filter(topic => topic.thumbnail_status === 'completed').length,
                repair_topics: repairTopics.length,
                visible_user_topics: visibleUserTopics.length,
            },
            workers: workerRows,
            jobs: jobRows,
            topics: newGenerationTopics,
            repair_topics: repairTopics,
            visible_user_topics: visibleUserTopics,
        })
    } catch (error: any) {
        console.error('[codex-worker] status load failed:', error)
        return NextResponse.json({ error: error?.message || 'Codex worker status load failed' }, { status: 500 })
    }
}

export async function POST(req: NextRequest) {
    const requester = await requireAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const body = await req.json().catch(() => ({}))
        const action = String(body.action || '').trim().toLowerCase()

        if (action === 'hide-visible-for-repair') {
            const superAdmin = await requireSuperAdmin(req)
            if (isAuthResponse(superAdmin)) return superAdmin

            const { data: candidates, error: candidateError } = await supabaseAdmin
                .from('topics_queue')
                .select('id,status,assigned_at,generated_title,progress_payload')
                .eq('status', 'pending')
                .is('assigned_at', null)
                .not('generated_title', 'is', null)
                .limit(1000)
            if (candidateError) throw candidateError

            const rows = (candidates || []).filter(topic => String(topic.generated_title || '').trim())
            const hiddenIds: string[] = []
            for (const topic of rows) {
                const progress = asObject(topic.progress_payload)
                const { data: hiddenTopic, error: updateError } = await supabaseAdmin
                    .from('topics_queue')
                    .update({
                        status: 'excluded',
                        progress_payload: {
                            ...progress,
                            admin_hidden: true,
                            admin_hidden_at: new Date().toISOString(),
                            admin_hidden_previous_status: 'pending',
                            repair_status: 'listed',
                        },
                    })
                    .eq('id', topic.id)
                    .eq('status', 'pending')
                    .is('assigned_at', null)
                    .select('id')
                    .maybeSingle()
                if (updateError) throw updateError
                if (hiddenTopic) hiddenIds.push(String(topic.id))
            }

            if (hiddenIds.length) {
                const { error: cacheError } = await supabaseAdmin
                    .from('user_topic_recommendations')
                    .delete()
                    .in('topic_queue_id', hiddenIds)
                if (cacheError) throw cacheError
            }

            return NextResponse.json({
                success: true,
                action,
                hidden_count: hiddenIds.length,
                hidden_topic_ids: hiddenIds,
            })
        }

        if (action === 'cancel') {
            const jobId = String(body.job_id || body.jobId || '').trim()
            if (!jobId) return NextResponse.json({ error: 'job_id is required' }, { status: 400 })
            const { data: job, error: jobError } = await supabaseAdmin
                .from('remote_hermes_queue')
                .select('id,status,job_type')
                .eq('id', jobId)
                .eq('job_type', CODEX_JOB_TYPE)
                .maybeSingle()
            if (jobError) throw jobError
            if (!job) return NextResponse.json({ error: 'Codex job not found' }, { status: 404 })
            if (String(job.status).toLowerCase() !== 'pending') {
                return NextResponse.json({ error: 'Only pending jobs can be cancelled safely' }, { status: 409 })
            }
            const { error } = await supabaseAdmin
                .from('remote_hermes_queue')
                .update({ status: 'canceled', worker_status: 'canceled', message: `Canceled by ${requester.user.email}` })
                .eq('id', jobId)
            if (error) throw error
            return NextResponse.json({ success: true, action: 'cancel', job_id: jobId })
        }

        if (action === 'retry') {
            const jobId = String(body.job_id || body.jobId || '').trim()
            if (!jobId) return NextResponse.json({ error: 'job_id is required' }, { status: 400 })
            const { data: previous, error: previousError } = await supabaseAdmin
                .from('remote_hermes_queue')
                .select('id,job_type,status,payload,attempt_number')
                .eq('id', jobId)
                .eq('job_type', CODEX_JOB_TYPE)
                .maybeSingle()
            if (previousError) throw previousError
            if (!previous) return NextResponse.json({ error: 'Codex job not found' }, { status: 404 })
            if (!['failed', 'error', 'canceled', 'cancelled'].includes(String(previous.status).toLowerCase())) {
                return NextResponse.json({ error: 'Only failed, errored, or cancelled jobs can be retried' }, { status: 409 })
            }
            const payload = { ...asObject(previous.payload), retry_of: previous.id, retried_by: requester.user.email, retried_at: new Date().toISOString() }
            const { data: job, error } = await supabaseAdmin
                .from('remote_hermes_queue')
                .insert({ job_type: CODEX_JOB_TYPE, payload, status: 'pending', priority: 10 })
                .select('id,status,created_at')
                .single()
            if (error) throw error
            return NextResponse.json({ success: true, action: 'retry', job })
        }

        if (action === 'queue') {
            const topicId = String(body.topic_id || body.topicId || '').trim()
            if (!topicId) return NextResponse.json({ error: 'topic_id is required' }, { status: 400 })
            const [{ data: topic, error: topicError }, { data: categories, error: categoryError }] = await Promise.all([
                supabaseAdmin.from('topics_queue').select('*').eq('id', topicId).maybeSingle(),
                supabaseAdmin.from('categories').select('id,name').limit(100),
            ])
            if (topicError) throw topicError
            if (categoryError) throw categoryError
            if (!topic) return NextResponse.json({ error: 'Topic not found' }, { status: 404 })
            if (String(topic.status || '').toLowerCase() !== 'pending') {
                return NextResponse.json({ error: 'Only pending, unclaimed topics can be queued from this page' }, { status: 409 })
            }
            const categoryName = (categories || []).find(category => String(category.id) === String(topic.category_id))?.name
            if (!categoryName) return NextResponse.json({ error: 'Topic category not found' }, { status: 409 })
            const { data: duplicate, error: duplicateError } = await supabaseAdmin
                .from('remote_hermes_queue')
                .select('id,status')
                .eq('job_type', CODEX_JOB_TYPE)
                .contains('payload', { topic_queue_id: topicId })
                .in('status', ACTIVE_JOB_STATUSES)
                .limit(1)
                .maybeSingle()
            if (duplicateError) throw duplicateError
            if (duplicate) return NextResponse.json({ error: `An active Codex job already exists: ${duplicate.id}` }, { status: 409 })
            const payload = topicPayload(topic, String(categoryName), requester.user.email || '')
            const { data: job, error: jobError } = await supabaseAdmin
                .from('remote_hermes_queue')
                .insert({ job_type: CODEX_JOB_TYPE, payload, status: 'pending', priority: 10, category_id: String(topic.category_id || '') || null })
                .select('id,status,created_at')
                .single()
            if (jobError) throw jobError
            const progress = asObject(topic.progress_payload)
            await supabaseAdmin.from('topics_queue').update({
                progress_payload: { ...progress, codex_generation_status: 'queued', codex_generation_job_id: job.id, codex_generation_requested_at: new Date().toISOString() },
            }).eq('id', topicId)
            return NextResponse.json({ success: true, action: 'queue', job })
        }

        return NextResponse.json({ error: 'Unsupported action' }, { status: 400 })
    } catch (error: any) {
        console.error('[codex-worker] action failed:', error)
        return NextResponse.json({ error: error?.message || 'Codex worker action failed' }, { status: 500 })
    }
}
