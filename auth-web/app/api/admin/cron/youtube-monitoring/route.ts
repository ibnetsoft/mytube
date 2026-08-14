import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const MONITORING_SLOTS_HOURS = [1, 6, 24, 72, 168, 336, 720]

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function parseDate(value: any): Date | null {
    if (!value) return null
    const date = new Date(String(value))
    return Number.isFinite(date.getTime()) ? date : null
}

function extractVideoId(metadata: any, videoUrl = '') {
    const candidates = [
        metadata?.videoId,
        metadata?.video_id,
        metadata?.youtube_video_id,
        metadata?.youtube_url,
        videoUrl,
    ]
    for (const candidate of candidates) {
        const text = String(candidate || '').trim()
        if (!text) continue
        if (/^[A-Za-z0-9_-]{11}$/.test(text)) return text
        for (const pattern of [/[?&]v=([A-Za-z0-9_-]{11})/, /youtu\.be\/([A-Za-z0-9_-]{11})/, /\/shorts\/([A-Za-z0-9_-]{11})/, /\/embed\/([A-Za-z0-9_-]{11})/]) {
            const match = text.match(pattern)
            if (match?.[1]) return match[1]
        }
    }
    return ''
}

function durationSeconds(value: string) {
    const match = String(value || '').match(/^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/)
    if (!match) return null
    return Number(match[1] || 0) * 86400 + Number(match[2] || 0) * 3600 + Number(match[3] || 0) * 60 + Number(match[4] || 0)
}

function splitKeys(value: any) {
    return String(value || '')
        .split(/[,;\r\n]+/)
        .map(item => item.trim())
        .filter(Boolean)
}

async function youtubeApiKeys(sb: any) {
    const envKeys = [...splitKeys(process.env.YOUTUBE_API_KEY), ...splitKeys(process.env.YOUTUBE_API_KEYS)]
    const { data } = await sb
        .from('global_settings')
        .select('key,value')
        .in('key', ['sys_api_youtube', 'sys_api_youtube_keys'])
    const remoteKeys = (data || []).flatMap((row: any) => splitKeys(row.value))
    return Array.from(new Set([...envKeys, ...remoteKeys])).slice(0, 5)
}

function nextDueSlot(metadata: any, publicAt: Date, now: Date) {
    const captured = new Set<number>((metadata?.youtube_monitoring?.captured_slots_hours || []).map((item: any) => Number(item)).filter(Number.isFinite))
    const hoursSincePublic = Math.max(0, Math.floor((now.getTime() - publicAt.getTime()) / 3600000))
    return MONITORING_SLOTS_HOURS.find(slot => slot <= hoursSincePublic && !captured.has(slot)) || null
}

function scoreMetrics(metrics: any, slotHours: number) {
    const views = Math.max(0, Number(metrics.views || 0))
    const likes = Math.max(0, Number(metrics.likes || 0))
    const comments = Math.max(0, Number(metrics.comments || 0))
    const viewsPerHour = views / Math.max(1, slotHours)
    const engagementRate = (likes + comments * 2) / Math.max(1, views)
    const reachScore = Math.min(40, (viewsPerHour / 25) * 40)
    const engagementScore = Math.min(35, (engagementRate / 0.04) * 35)
    const commentScore = Math.min(15, ((comments / Math.max(1, views / 1000)) / 20) * 15)
    const freshnessScore = slotHours <= 24 ? 10 : slotHours <= 168 ? 6 : 3
    const performanceScore = Math.round((reachScore + engagementScore + commentScore + freshnessScore) * 100) / 100
    const outcomeLabel =
        performanceScore >= 75 ? 'winner'
        : engagementRate >= 0.04 && viewsPerHour < 10 ? 'retention_good_low_reach'
        : performanceScore >= 45 ? 'promising'
        : viewsPerHour < 3 ? 'underperforming'
        : 'neutral'
    return {
        performance_score: performanceScore,
        outcome_label: outcomeLabel,
        views_per_hour: Math.round(viewsPerHour * 100) / 100,
        engagement_rate: Math.round(engagementRate * 100000) / 100000,
    }
}

function learningSummary(metrics: any, score: any, slotHours: number) {
    const recommendations =
        score.outcome_label === 'winner'
            ? ['Reuse this title/topic pattern as a positive reference.', 'Prioritize similar opening structure and metadata tone.']
            : score.outcome_label === 'retention_good_low_reach'
                ? ['Content engagement is acceptable; test a stronger title and thumbnail.']
                : score.outcome_label === 'underperforming'
                    ? ['Avoid repeating this exact title/topic packaging without revision.', 'Review hook, thumbnail promise, and category fit before generating similar videos.']
                    : ['Keep as neutral benchmark data until later capture slots mature.']
    return {
        summary: `${slotHours}h public capture: ${metrics.views || 0} views, ${metrics.likes || 0} likes, ${metrics.comments || 0} comments. Score ${score.performance_score} (${score.outcome_label}).`,
        recommendations,
    }
}

async function fetchVideoMetrics(videoId: string, apiKeys: string[]) {
    const failures: string[] = []
    let data: any = null
    for (let i = 0; i < apiKeys.length; i += 1) {
        const params = new URLSearchParams({ part: 'snippet,statistics,contentDetails', id: videoId, key: apiKeys[i] })
        const res = await fetch(`https://www.googleapis.com/youtube/v3/videos?${params.toString()}`, { cache: 'no-store' })
        if (res.ok) {
            data = await res.json()
            break
        }
        const body = (await res.text()).slice(0, 200)
        failures.push(`key ${i + 1}: HTTP ${res.status}: ${body}`)
        if (![403, 429, 500, 502, 503, 504].includes(res.status) && !body.toLowerCase().includes('api key')) break
    }
    if (!data) throw new Error(`YouTube Data API failed after ${failures.length} key(s): ${failures.join(' | ')}`)
    const item = data?.items?.[0]
    if (!item) throw new Error('Video not found or not accessible through YouTube Data API.')
    const stats = item.statistics || {}
    const snippet = item.snippet || {}
    return {
        video_id: videoId,
        title: snippet.title || '',
        channel_id: snippet.channelId || '',
        channel_title: snippet.channelTitle || '',
        published_at: snippet.publishedAt || '',
        duration_seconds: durationSeconds(item.contentDetails?.duration || ''),
        views: Number(stats.viewCount || 0),
        likes: Number(stats.likeCount || 0),
        comments: Number(stats.commentCount || 0),
        raw_payload: item,
    }
}

export async function GET(req: Request) {
    const authHeader = req.headers.get('authorization')
    if (!process.env.CRON_SECRET || authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
        return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    }

    const dryRun = new URL(req.url).searchParams.get('dry_run') === 'true'
    const sb = getAdmin()
    const apiKeys = await youtubeApiKeys(sb)
    if (!apiKeys.length) return NextResponse.json({ success: false, error: 'YOUTUBE_API_KEY is not configured' }, { status: 500 })

    const { data: requests, error } = await sb
        .from('publishing_requests')
        .select('id,user_id,video_url,status,metadata,created_at')
        .eq('status', 'public')
        .order('created_at', { ascending: false })
        .limit(100)
    if (error) throw error

    const now = new Date()
    const results: any[] = []

    for (const request of requests || []) {
        const metadata = request.metadata || {}
        const videoId = extractVideoId(metadata, request.video_url || '')
        if (!videoId) continue
        const publicAt = parseDate(metadata.made_public_at) || parseDate(metadata.published_at) || parseDate(request.created_at)
        if (!publicAt) continue
        const slotHours = nextDueSlot(metadata, publicAt, now)
        if (!slotHours) continue

        try {
            const metrics = await fetchVideoMetrics(videoId, apiKeys)
            const score = scoreMetrics(metrics, slotHours)
            const learning = learningSummary(metrics, score, slotHours)
            const generationContext = {
                title: metadata.title || metrics.title,
                description: metadata.description || null,
                tags: metadata.tags || null,
                hashtags: metadata.hashtags || null,
                category_id: metadata.category_id || null,
                channel_id: metadata.channel_id || null,
                app_mode: metadata.app_mode || null,
                track_count: metadata.track_count || null,
                total_duration_seconds: metadata.total_duration_seconds || metrics.duration_seconds,
                source: metadata.source || null,
            }
            const metricPayload = {
                sync_key: `ytmetric:${videoId}:${slotHours}`,
                publishing_request_id: request.id,
                user_id: request.user_id,
                local_project_id: metadata.project_id || null,
                video_id: videoId,
                captured_at: now.toISOString(),
                hours_since_public: slotHours,
                views: metrics.views,
                likes: metrics.likes,
                comments: metrics.comments,
                duration_seconds: metrics.duration_seconds,
                score,
                metadata: generationContext,
                raw_payload: metrics.raw_payload,
            }
            const snapshotPayload = {
                sync_key: `ytlearning:${videoId}:${slotHours}`,
                publishing_request_id: request.id,
                user_id: request.user_id,
                local_project_id: metadata.project_id || null,
                video_id: videoId,
                captured_at: now.toISOString(),
                hours_since_public: slotHours,
                performance_score: score.performance_score,
                outcome_label: score.outcome_label,
                learning_summary: learning.summary,
                recommendations: learning.recommendations,
                metrics: metricPayload,
                generation_context: generationContext,
            }
            if (!dryRun) {
                await sb.from('youtube_video_metrics').upsert(metricPayload, { onConflict: 'sync_key' })
                await sb.from('video_learning_snapshots').upsert(snapshotPayload, { onConflict: 'sync_key' })
                if (metadata.project_id) {
                    await sb.from('project_learning_events').upsert({
                        sync_key: `event:youtube_monitor:${videoId}:${slotHours}`,
                        local_event_id: null,
                        local_project_id: metadata.project_id,
                        project_sync_id: metadata.project_sync_id || null,
                        user_id: request.user_id,
                        employee_email: metadata.employee_email || null,
                        project_name: metadata.project_name || metadata.title || '',
                        project_topic: metadata.topic || '',
                        event_type: 'youtube_public_metrics_captured',
                        stage: 'youtube_monitoring',
                        source: 'youtube_monitoring_cron',
                        payload: snapshotPayload,
                        local_created_at: now.toISOString(),
                        synced_at: now.toISOString(),
                    }, { onConflict: 'sync_key' })
                }
                const capturedSlots = Array.from(new Set([...(metadata.youtube_monitoring?.captured_slots_hours || []), slotHours])).sort((a: any, b: any) => Number(a) - Number(b))
                await sb.from('publishing_requests').update({
                    metadata: {
                        ...metadata,
                        youtube_monitoring: {
                            ...(metadata.youtube_monitoring || {}),
                            captured_slots_hours: capturedSlots,
                            last_captured_at: now.toISOString(),
                            last_slot_hours: slotHours,
                            last_metrics: {
                                views: metrics.views,
                                likes: metrics.likes,
                                comments: metrics.comments,
                                ...score,
                            },
                        },
                    },
                }).eq('id', request.id)
            }
            results.push({ request_id: request.id, video_id: videoId, slot_hours: slotHours, score })
        } catch (e: any) {
            results.push({ request_id: request.id, video_id: videoId, slot_hours: slotHours, error: e.message })
        }
    }

    return NextResponse.json({
        success: true,
        dryRun,
        scanned: requests?.length || 0,
        due: results.length,
        captured: results.filter(row => !row.error).length,
        failed: results.filter(row => row.error).length,
        results,
    })
}
