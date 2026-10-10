import { NextResponse } from 'next/server'
import { createHash, timingSafeEqual } from 'crypto'
import { supabaseAdmin as db } from '@/lib/supabaseAdmin'
import { loadStdProjectAssets } from '@/lib/stdProjectAssets'
import { currentAeMouthJob, reviewedAeMouthAssets } from '@/lib/stdAeMouth'
import { enqueueStdProjectRender } from '@/lib/stdRenderQueue'
export const dynamic = 'force-dynamic'
export const maxDuration = 300

export async function POST(req: Request) {
    // Existing source workers already hold this credential for their database lease.
    const expected = process.env.SUPABASE_SERVICE_ROLE_KEY || ''
    const supplied = (req.headers.get('authorization') || '').replace(/^Bearer /, '')
    if (!expected || Buffer.byteLength(expected) !== Buffer.byteLength(supplied) ||
        !timingSafeEqual(Buffer.from(expected), Buffer.from(supplied)))
        return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    try {
        const { projectId, jobId, workerToken } = await req.json()
        if (![projectId, jobId, workerToken].every(v => typeof v === 'string' && /^[a-zA-Z0-9-]{1,80}$/.test(v)))
            return NextResponse.json({ error: 'Invalid request' }, { status: 400 })
        const [p, s, a] = await Promise.all([
            db.from('std_projects').select('*').eq('id', projectId).single(),
            db.from('std_project_scenes').select('*').eq('project_id', projectId).order('scene_number'),
            loadStdProjectAssets(db, projectId, '*'),
        ])
        if (p.error || s.error || a.error) throw p.error || s.error || a.error
        if (['approved', 'canceled'].includes(p.data.status)) throw new Error('Project is closed')
        const job = currentAeMouthJob(p.data, s.data, a.data || [])
        if (job?.id !== jobId || !job.metadata.automatic || job.metadata.worker_token !== workerToken ||
            job.metadata.state !== 'processing' || job.metadata.phase !== 'auto_enqueue')
            throw new Error('Current reviewed job and worker lease are required')
        reviewedAeMouthAssets(p.data, s.data, a.data || [])
        // Stable primary key survives a lost HTTP response, even after rendering completes.
        const h = createHash('sha256').update(`ae-final:${jobId}`).digest('hex')
        const taskId = `${h.slice(0,8)}-${h.slice(8,12)}-5${h.slice(13,16)}-a${h.slice(17,20)}-${h.slice(20,32)}`
        const queue = await enqueueStdProjectRender(projectId, { jobId, taskId })
        const now = new Date().toISOString()
        const latest = await db.from('std_project_submissions').select('id,metadata')
            .eq('project_id', projectId).order('created_at', { ascending: false }).limit(1).maybeSingle()
        if (!latest.error && latest.data?.id) {
            await db.from('std_project_submissions').update({
                status: 'review_requested',
                metadata: {
                    ...(latest.data.metadata || {}),
                    postprocess_status: 'complete',
                    ae_mouth_job_id: jobId,
                    remote_render_queue_id: queue.id,
                    final_render_enqueued_at: now,
                },
            }).eq('id', latest.data.id)
        }
        await db.from('std_projects').update({
            progress_payload: {
                ...(p.data.progress_payload || {}),
                postprocess_status: 'complete',
                ae_mouth_job_id: jobId,
                remote_task_id: queue.id,
                remote_render_queue_id: queue.id,
                submitted_to_render_queue_at: now,
                admin_publish_status: 'render_pending',
            },
            updated_at: now,
        }).eq('id', projectId)
        return NextResponse.json({ render_queue_id: queue.id, status: queue.status })
    } catch (error: any) {
        const pendingCode = ['VIDEO_TAIL_PENDING', 'SCENE_POSTPROCESS_PENDING'].includes(error.code) ? error.code : 'REGISTRATION_FAILED'
        return NextResponse.json({ error: error.message || 'Automatic render registration failed', code: pendingCode }, { status: 409 })
    }
}
