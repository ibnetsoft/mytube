import { NextRequest, NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../_auth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

const CODEX_JOB_TYPE = 'codex_content_generate'
const ACTIVE_JOB_STATUSES = ['pending', 'claimed', 'rendering', 'running']

const asObject = (value: unknown): Record<string, any> => (
    value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : {}
)

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
        const [{ data: categories, error: categoriesError }, { data: topics, error: topicsError }, { data: jobs, error: jobsError }, { data: workers, error: workersError }] = await Promise.all([
            supabaseAdmin.from('categories').select('id,name').limit(100),
            supabaseAdmin
                .from('topics_queue')
                .select('id,topic,generated_title,category_id,status,language,assigned_duration_minutes,recommended_duration_minutes,pregenerated_script_status,pregenerated_structure_status,pregenerated_structure,progress_payload,created_at')
                .order('created_at', { ascending: false })
                .limit(100),
            supabaseAdmin
                .from('remote_hermes_queue')
                .select('id,job_type,status,worker_status,progress,message,error_message,payload,worker_id,created_at,completed_at,attempt_number')
                .eq('job_type', CODEX_JOB_TYPE)
                .order('created_at', { ascending: false })
                .limit(100),
            supabaseAdmin.from('workers').select('worker_id,worker_group,last_heartbeat_at,allowed_job_types').order('registered_at', { ascending: false }),
        ])
        if (categoriesError) throw categoriesError
        if (topicsError) throw topicsError
        if (jobsError) throw jobsError
        if (workersError) throw workersError

        const categoryNames = new Map((categories || []).map(category => [String(category.id), String(category.name || '')]))
        const now = Date.now()
        const workerRows = (workers || []).map(worker => ({
            ...worker,
            online: Boolean(worker.last_heartbeat_at) && now - new Date(worker.last_heartbeat_at).getTime() < 90_000,
            supports_codex: Array.isArray(worker.allowed_job_types) && worker.allowed_job_types.includes(CODEX_JOB_TYPE),
        }))
        const jobRows = (jobs || []).map(job => ({
            ...job,
            topic_queue_id: String(asObject(job.payload).topic_queue_id || ''),
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
                category_id: topic.category_id,
                category_name: categoryNames.get(String(topic.category_id)) || `카테고리 ${topic.category_id}`,
                status: topic.status,
                language: topic.language || 'ko',
                duration_minutes: Number(topic.assigned_duration_minutes || topic.recommended_duration_minutes || 0),
                script_status: topic.pregenerated_script_status || progress.pregenerated_script_status || 'not_ready',
                structure_status: topic.pregenerated_structure_status || progress.pregenerated_structure_status || 'not_ready',
                scene_count: scenes.length || Number(structure.scene_count || 0),
                image_count: scenes.filter((scene: any) => Boolean(scene?.image_url)).length,
                thumbnail_status: progress.thumbnail_generation_status || (progress.thumbnail_bg_url ? 'completed' : 'not_started'),
                thumbnail_url: progress.thumbnail_bg_url || '',
                worker_id: '',
                latest_job: latestJobByTopic.get(String(topic.id)) || null,
                created_at: topic.created_at,
            }
        })
        const activeJobs = jobRows.filter(job => ACTIVE_JOB_STATUSES.includes(String(job.status || '').toLowerCase()))

        return NextResponse.json({
            generated_at: new Date().toISOString(),
            summary: {
                total_topics: topicRows.length,
                prepared_topics: topicRows.filter(topic => topic.script_status === 'ready').length,
                active_jobs: activeJobs.length,
                failed_jobs: jobRows.filter(job => ['failed', 'error'].includes(String(job.status || '').toLowerCase())).length,
                thumbnails_completed: topicRows.filter(topic => topic.thumbnail_status === 'completed').length,
            },
            workers: workerRows,
            jobs: jobRows,
            topics: topicRows,
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
