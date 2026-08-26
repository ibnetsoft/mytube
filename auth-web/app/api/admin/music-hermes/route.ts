import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../_auth'
import {
    enqueueMusicPromptPackFromTrendJob,
    enqueueMusicPromptPackGenerateJob,
    enqueueMusicTrendAnalyzeJob,
} from '../../../../lib/musicHermesTrigger'
import {
    dispatchMusicPromptPackToStdQueue,
    findThaiMusicQueueCandidates,
} from '../../../../lib/musicHermesStdQueue'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json().catch(() => ({}))
        const action = String(body.action || body.jobType || 'pipeline').trim().toLowerCase()
        const force = Boolean(body.force)
        const supabase = getAdmin()

        if (action === 'music_trend_analyze' || action === 'trend') {
            const result = await enqueueMusicTrendAnalyzeJob(supabase, body, { force })
            if (result.outcome === 'skipped') {
                return NextResponse.json({ error: result.reason }, { status: 409 })
            }
            return NextResponse.json({ success: true, action: 'music_trend_analyze', reused: result.outcome === 'reused', job: result.job })
        }

        if (action === 'music_prompt_pack_generate' || action === 'prompt') {
            const result = await enqueueMusicPromptPackGenerateJob(supabase, body, { force })
            if (result.outcome === 'skipped') {
                return NextResponse.json({ error: result.reason }, { status: 409 })
            }
            return NextResponse.json({ success: true, action: 'music_prompt_pack_generate', reused: result.outcome === 'reused', job: result.job })
        }

        if (action === 'pipeline') {
            const trendResult = await enqueueMusicTrendAnalyzeJob(supabase, {
                ...body,
                enqueue_prompt_pack_on_complete: true,
            }, { force })

            if (trendResult.outcome === 'skipped') {
                return NextResponse.json({ error: trendResult.reason }, { status: 409 })
            }

            let promptResult: any = null
            if (trendResult.outcome === 'reused' && trendResult.job?.result_payload) {
                promptResult = await enqueueMusicPromptPackFromTrendJob(supabase, trendResult.job, { force })
            }

            return NextResponse.json({
                success: true,
                action: 'pipeline',
                trend: {
                    reused: trendResult.outcome === 'reused',
                    job: trendResult.job,
                },
                prompt_pack: promptResult
                    ? {
                        reused: promptResult.outcome === 'reused',
                        deferred: false,
                        job: promptResult.job,
                    }
                    : {
                        reused: false,
                        deferred: true,
                        reason: 'queued_after_trend_completion',
                    },
            })
        }

        if (action === 'dispatch' || action === 'dispatch_prompt_pack' || action === 'queue_to_thailand') {
            const promptJobId = String(body.prompt_pack_job_id || body.promptJobId || '').trim()
            const targetUserEmail = String(body.target_user_email || body.targetUserEmail || '').trim().toLowerCase()

            let promptPackJob: any = null
            if (promptJobId) {
                const { data, error } = await supabase
                    .from('remote_hermes_queue')
                    .select('id, job_type, status, result_payload, payload, created_at, completed_at')
                    .eq('id', promptJobId)
                    .eq('job_type', 'music_prompt_pack_generate')
                    .maybeSingle()
                if (error) throw error
                promptPackJob = data
            } else {
                const targetMarket = String(body.target_market || 'Thailand').trim()
                const playlistConcept = String(body.playlist_concept || '').trim()
                const trackCount = Number.parseInt(String(body.track_count || '60'), 10) || 60
                const trackDurationSeconds = Number.parseInt(String(body.track_duration_seconds || '180'), 10) || 180
                const queueKey = [
                    'music-hermes',
                    'music_prompt_pack_generate',
                    targetMarket.toLowerCase(),
                    (playlistConcept || (targetMarket.toLowerCase() === 'thailand'
                        ? 'relaxing thai cafe lofi for work and study'
                        : 'relaxing instrumental lofi and ambient mix for deep focus')).toLowerCase(),
                    String(trackCount),
                    String(trackDurationSeconds),
                ].join(':')
                const { data, error } = await supabase
                    .from('remote_hermes_queue')
                    .select('id, job_type, status, result_payload, payload, created_at, completed_at')
                    .eq('job_type', 'music_prompt_pack_generate')
                    .contains('payload', { queue_key: queueKey })
                    .order('created_at', { ascending: false })
                    .limit(1)
                    .maybeSingle()
                if (error) throw error
                promptPackJob = data
            }

            if (!promptPackJob) {
                return NextResponse.json({ error: 'Completed prompt pack job not found' }, { status: 404 })
            }
            if (promptPackJob.status !== 'completed' || !promptPackJob.result_payload) {
                return NextResponse.json({ error: 'Prompt pack job is not completed yet' }, { status: 409 })
            }

            let dispatchTarget = targetUserEmail
            if (!dispatchTarget) {
                const candidates = await findThaiMusicQueueCandidates(supabase)
                dispatchTarget = String(candidates[0]?.email || '').trim().toLowerCase()
            }
            if (!dispatchTarget) {
                return NextResponse.json({ error: 'No approved Thailand worker found for dispatch' }, { status: 404 })
            }

            const dispatched = await dispatchMusicPromptPackToStdQueue(
                supabase,
                promptPackJob.result_payload,
                dispatchTarget,
            )

            return NextResponse.json({
                success: true,
                action: 'dispatch_prompt_pack',
                prompt_pack_job: {
                    id: promptPackJob.id,
                    status: promptPackJob.status,
                    completed_at: promptPackJob.completed_at,
                },
                dispatch: {
                    reused: dispatched.reused,
                    target_user_email: dispatchTarget,
                    topic: dispatched.topic,
                    category: dispatched.category,
                    recommendation_inserted: dispatched.recommendation_inserted,
                },
            })
        }

        return NextResponse.json({ error: 'Unsupported action' }, { status: 400 })
    } catch (e: any) {
        console.error('[music-hermes] Failed to enqueue job:', e)
        return NextResponse.json({ error: e?.message || 'Failed to enqueue music Hermes job' }, { status: 500 })
    }
}

export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const targetMarket = String(searchParams.get('target_market') || searchParams.get('targetMarket') || 'Thailand').trim()
        const playlistConcept = String(searchParams.get('playlist_concept') || searchParams.get('playlistConcept') || '').trim()
        const trackCount = Number.parseInt(String(searchParams.get('track_count') || searchParams.get('trackCount') || '60'), 10) || 60
        const trackDurationSeconds = Number.parseInt(String(searchParams.get('track_duration_seconds') || searchParams.get('trackDurationSeconds') || '180'), 10) || 180

        const queueKeyBase = [
            targetMarket.trim().toLowerCase(),
            playlistConcept.trim().toLowerCase() || (targetMarket.toLowerCase() === 'thailand' ? 'relaxing thai cafe lofi for work and study' : 'relaxing instrumental lofi and ambient mix for deep focus'),
            String(trackCount),
            String(trackDurationSeconds),
        ]
        const trendQueueKey = ['music-hermes', 'music_trend_analyze', ...queueKeyBase].join(':')
        const promptQueueKey = ['music-hermes', 'music_prompt_pack_generate', ...queueKeyBase].join(':')

        const supabase = getAdmin()
        const [{ data: trendJob, error: trendError }, { data: promptJob, error: promptError }] = await Promise.all([
            supabase
                .from('remote_hermes_queue')
                .select('id, job_type, status, worker_status, progress, message, result_payload, error_message, created_at, completed_at, payload')
                .eq('job_type', 'music_trend_analyze')
                .contains('payload', { queue_key: trendQueueKey })
                .order('created_at', { ascending: false })
                .limit(1)
                .maybeSingle(),
            supabase
                .from('remote_hermes_queue')
                .select('id, job_type, status, worker_status, progress, message, result_payload, error_message, created_at, completed_at, payload')
                .eq('job_type', 'music_prompt_pack_generate')
                .contains('payload', { queue_key: promptQueueKey })
                .order('created_at', { ascending: false })
                .limit(1)
                .maybeSingle(),
        ])

        if (trendError) throw trendError
        if (promptError) throw promptError

        const thaiCandidates = await findThaiMusicQueueCandidates(supabase)

        return NextResponse.json({
            trend_job: trendJob || null,
            prompt_pack_job: promptJob || null,
            target_candidates: thaiCandidates,
        })
    } catch (e: any) {
        console.error('[music-hermes] Failed to fetch job status:', e)
        return NextResponse.json({ error: e?.message || 'Failed to fetch music Hermes status' }, { status: 500 })
    }
}
