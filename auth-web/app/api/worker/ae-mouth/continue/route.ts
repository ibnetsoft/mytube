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
        return NextResponse.json({ render_queue_id: queue.id, status: queue.status })
    } catch (error: any) {
        return NextResponse.json({ error: error.message || 'Automatic render registration failed', code: error.code === 'VIDEO_TAIL_PENDING' ? 'VIDEO_TAIL_PENDING' : 'REGISTRATION_FAILED' }, { status: 409 })
    }
}
