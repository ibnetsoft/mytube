import type { SupabaseClient } from '@supabase/supabase-js'

const MUSIC_QUEUE_FRESHNESS_HOURS = 24

type MusicHermesJobType = 'music_trend_analyze' | 'music_prompt_pack_generate'

export type MusicHermesRequest = {
    target_market?: string | null
    playlist_concept?: string | null
    track_count?: number | null
    track_duration_seconds?: number | null
    source_evidence_summary?: Record<string, any> | null
    trend_analysis?: Record<string, any> | null
    enqueue_prompt_pack_on_complete?: boolean | null
}

export type EnqueueMusicHermesResult =
    | { outcome: 'reused'; job: any }
    | { outcome: 'enqueued'; job: any }
    | { outcome: 'skipped'; reason: string }

function normalizeTargetMarket(value: any): string {
    const text = String(value || '').trim()
    return text || 'Thailand'
}

function normalizePlaylistConcept(value: any, targetMarket: string): string {
    const text = String(value || '').trim()
    if (text) return text
    if (targetMarket.toLowerCase() === 'thailand') return 'Relaxing Thai cafe lofi for work and study'
    return 'Relaxing instrumental lofi and ambient mix for deep focus'
}

function boundedInt(value: any, min: number, max: number, fallback: number): number {
    const parsed = Number.parseInt(String(value ?? ''), 10)
    if (!Number.isFinite(parsed)) return fallback
    return Math.max(min, Math.min(max, parsed))
}

function objectOrEmpty(value: any): Record<string, any> {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
}

function queueKey(jobType: MusicHermesJobType, targetMarket: string, playlistConcept: string, trackCount: number, trackDurationSeconds: number): string {
    return [
        'music-hermes',
        jobType,
        targetMarket.trim().toLowerCase(),
        playlistConcept.trim().toLowerCase(),
        String(trackCount),
        String(trackDurationSeconds),
    ].join(':')
}

function buildBasePayload(body: MusicHermesRequest) {
    const targetMarket = normalizeTargetMarket(body.target_market)
    const playlistConcept = normalizePlaylistConcept(body.playlist_concept, targetMarket)
    const trackCount = boundedInt(body.track_count, 1, 200, 60)
    const trackDurationSeconds = boundedInt(body.track_duration_seconds, 30, 1800, 180)
    return {
        targetMarket,
        playlistConcept,
        trackCount,
        trackDurationSeconds,
        sourceEvidenceSummary: objectOrEmpty(body.source_evidence_summary),
    }
}

async function findReusableJob(
    supabase: SupabaseClient,
    jobType: MusicHermesJobType,
    key: string,
): Promise<EnqueueMusicHermesResult | null> {
    const freshCutoff = new Date(Date.now() - MUSIC_QUEUE_FRESHNESS_HOURS * 60 * 60 * 1000).toISOString()
    const { data: recent } = await supabase
        .from('remote_hermes_queue')
        .select('id, job_type, status, result_payload, completed_at, created_at, payload')
        .eq('job_type', jobType)
        .contains('payload', { queue_key: key })
        .eq('status', 'completed')
        .gte('completed_at', freshCutoff)
        .order('completed_at', { ascending: false })
        .limit(1)
        .maybeSingle()

    if (recent) return { outcome: 'reused', job: recent }

    const { data: inFlight } = await supabase
        .from('remote_hermes_queue')
        .select('id, job_type, status, created_at, payload')
        .eq('job_type', jobType)
        .contains('payload', { queue_key: key })
        .in('status', ['pending', 'rendering'])
        .order('created_at', { ascending: false })
        .limit(1)
        .maybeSingle()

    if (inFlight) return { outcome: 'skipped', reason: 'already_in_flight' }
    return null
}

export async function enqueueMusicTrendAnalyzeJob(
    supabase: SupabaseClient,
    body: MusicHermesRequest,
    opts: { force?: boolean } = {}
): Promise<EnqueueMusicHermesResult> {
    const { targetMarket, playlistConcept, trackCount, trackDurationSeconds, sourceEvidenceSummary } = buildBasePayload(body)
    const key = queueKey('music_trend_analyze', targetMarket, playlistConcept, trackCount, trackDurationSeconds)

    if (!opts.force) {
        const existing = await findReusableJob(supabase, 'music_trend_analyze', key)
        if (existing) return existing
    }

    const payload = {
        queue_key: key,
        target_market: targetMarket,
        playlist_concept: playlistConcept,
        track_count: trackCount,
        track_duration_seconds: trackDurationSeconds,
        source_evidence_summary: sourceEvidenceSummary,
        enqueue_prompt_pack_on_complete: Boolean(body.enqueue_prompt_pack_on_complete),
    }

    const { data: inserted, error } = await supabase
        .from('remote_hermes_queue')
        .insert({
            job_type: 'music_trend_analyze',
            category_id: key,
            payload,
            status: 'pending',
        })
        .select('id, job_type, status, created_at, payload')
        .single()

    if (error) throw error
    return { outcome: 'enqueued', job: inserted }
}

export async function enqueueMusicPromptPackGenerateJob(
    supabase: SupabaseClient,
    body: MusicHermesRequest,
    opts: { force?: boolean } = {}
): Promise<EnqueueMusicHermesResult> {
    const { targetMarket, playlistConcept, trackCount, trackDurationSeconds, sourceEvidenceSummary } = buildBasePayload(body)
    const trendAnalysis = objectOrEmpty(body.trend_analysis)
    const key = queueKey('music_prompt_pack_generate', targetMarket, playlistConcept, trackCount, trackDurationSeconds)

    if (!opts.force) {
        const existing = await findReusableJob(supabase, 'music_prompt_pack_generate', key)
        if (existing) return existing
    }

    const payload = {
        queue_key: key,
        target_market: targetMarket,
        playlist_concept: playlistConcept,
        track_count: trackCount,
        track_duration_seconds: trackDurationSeconds,
        source_evidence_summary: sourceEvidenceSummary,
        trend_analysis: trendAnalysis,
    }

    const { data: inserted, error } = await supabase
        .from('remote_hermes_queue')
        .insert({
            job_type: 'music_prompt_pack_generate',
            category_id: key,
            payload,
            status: 'pending',
        })
        .select('id, job_type, status, created_at, payload')
        .single()

    if (error) throw error
    return { outcome: 'enqueued', job: inserted }
}

export async function enqueueMusicPromptPackFromTrendJob(
    supabase: SupabaseClient,
    trendJob: any,
    opts: { force?: boolean } = {}
): Promise<EnqueueMusicHermesResult> {
    const payload = objectOrEmpty(trendJob?.payload)
    const resultPayload = objectOrEmpty(trendJob?.result_payload)
    return enqueueMusicPromptPackGenerateJob(
        supabase,
        {
            target_market: resultPayload.target_market || payload.target_market,
            playlist_concept: resultPayload.playlist_concept || payload.playlist_concept,
            track_count: resultPayload.track_count || payload.track_count,
            track_duration_seconds: resultPayload.track_duration_seconds || payload.track_duration_seconds,
            source_evidence_summary: resultPayload.source_evidence_summary || payload.source_evidence_summary,
            trend_analysis: resultPayload,
        },
        opts,
    )
}
