import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../_auth'
import { syncContentFeedbackToNotion } from '@/lib/notionLearningSync'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

function countBy(rows: any[], key: string) {
    const map = new Map<string, number>()
    for (const row of rows || []) {
        const value = String(row?.[key] || 'unknown')
        map.set(value, (map.get(value) || 0) + 1)
    }
    return Array.from(map.entries())
        .map(([name, count]) => ({ [key]: name, count }))
        .sort((a: any, b: any) => b.count - a.count || String(a[key]).localeCompare(String(b[key])))
}

function buildProjectRows(events: any[], limit: number) {
    const map = new Map<string, any>()
    for (const event of events || []) {
        const projectId = event.local_project_id || 'unknown'
        const key = String(projectId)
        const existing = map.get(key) || {
            project_id: projectId,
            name: event.project_name || '',
            topic: event.project_topic || '',
            event_count: 0,
            last_event_at: event.local_created_at || event.created_at || '',
        }
        existing.event_count += 1
        const eventTime = event.local_created_at || event.created_at || ''
        if (String(eventTime) > String(existing.last_event_at || '')) existing.last_event_at = eventTime
        map.set(key, existing)
    }
    return Array.from(map.values())
        .sort((a, b) => String(b.last_event_at || '').localeCompare(String(a.last_event_at || '')))
        .slice(0, limit)
}

function summarizeContentFeedback(rows: any[]) {
    const titleScores = rows
        .map((row: any) => Number(row.title_score))
        .filter((value: number) => Number.isFinite(value))
    const scriptScores = rows
        .map((row: any) => Number(row.script_score))
        .filter((value: number) => Number.isFinite(value))
    const avg = (values: number[]) => values.length
        ? Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100) / 100
        : null

    return {
        total_feedback: rows.length,
        quality_counts: countBy(rows, 'outcome_quality'),
        source_counts: countBy(rows, 'feedback_source'),
        category_counts: countBy(rows, 'category_name'),
        average_title_score: avg(titleScores),
        average_script_score: avg(scriptScores),
        recent_feedback: rows.slice(0, 50).map((row: any) => ({
            id: row.id,
            topic_queue_id: row.topic_queue_id,
            category_id: row.category_id,
            category_name: row.category_name,
            feedback_source: row.feedback_source,
            outcome_quality: row.outcome_quality,
            generated_title: row.generated_title,
            production_topic: row.production_topic,
            title_score: row.title_score,
            script_score: row.script_score,
            reviewer_email: row.reviewer_email,
            reviewer_note: row.reviewer_note,
            metrics: row.metrics || {},
            created_at: row.created_at,
            updated_at: row.updated_at,
        })),
    }
}

function summarizeYoutubeLearning(metricsRows: any[], snapshotRows: any[]) {
    const latestByVideo = new Map<string, any>()
    for (const row of metricsRows || []) {
        const videoId = String(row.video_id || '')
        if (!videoId) continue
        const existing = latestByVideo.get(videoId)
        if (!existing || String(row.captured_at || '') > String(existing.captured_at || '')) {
            latestByVideo.set(videoId, row)
        }
    }

    const latest = Array.from(latestByVideo.values())
    const scores = (snapshotRows || [])
        .map((row: any) => Number(row.performance_score))
        .filter((value: number) => Number.isFinite(value))
    const avgScore = scores.length
        ? Math.round((scores.reduce((sum: number, value: number) => sum + value, 0) / scores.length) * 100) / 100
        : null

    return {
        total_metric_captures: (metricsRows || []).length,
        monitored_videos: latest.length,
        average_performance_score: avgScore,
        outcome_counts: countBy(snapshotRows || [], 'outcome_label'),
        latest_metrics: latest
            .sort((a: any, b: any) => String(b.captured_at || '').localeCompare(String(a.captured_at || '')))
            .slice(0, 20)
            .map((row: any) => ({
                video_id: row.video_id,
                local_project_id: row.local_project_id,
                captured_at: row.captured_at,
                hours_since_public: row.hours_since_public,
                views: row.views,
                likes: row.likes,
                comments: row.comments,
                score: row.score || {},
                title: row.metadata?.title || row.raw_payload?.snippet?.title || '',
            })),
        recent_learning: (snapshotRows || []).slice(0, 20).map((row: any) => ({
            video_id: row.video_id,
            local_project_id: row.local_project_id,
            captured_at: row.captured_at,
            hours_since_public: row.hours_since_public,
            performance_score: row.performance_score,
            outcome_label: row.outcome_label,
            learning_summary: row.learning_summary,
            recommendations: row.recommendations || [],
            title: row.generation_context?.title || '',
        })),
    }
}

export async function GET(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const limit = Math.max(1, Math.min(500, Number.parseInt(searchParams.get('limit') || '100', 10) || 100))
        const categoryId = searchParams.get('categoryId')
        const supabase = getAdmin()

        const { data: events, error } = await supabase
            .from('project_learning_events')
            .select('*')
            .order('local_created_at', { ascending: false, nullsFirst: false })
            .order('created_at', { ascending: false })
            .limit(Math.max(limit, 2000))

        if (error) throw error

        const { count: snapshotCount, error: snapshotError } = await supabase
            .from('project_learning_snapshots')
            .select('id', { count: 'exact', head: true })

        if (snapshotError) throw snapshotError

        let feedbackQuery = supabase
            .from('content_generation_feedback')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(Math.max(limit, 500))

        if (categoryId && categoryId !== 'all') {
            feedbackQuery = feedbackQuery.eq('category_id', categoryId)
        }

        const { data: feedbackRows, error: feedbackError } = await feedbackQuery
        if (feedbackError && !String(feedbackError.message || '').includes('content_generation_feedback')) {
            throw feedbackError
        }

        const { data: youtubeMetricsRows, error: youtubeMetricsError } = await supabase
            .from('youtube_video_metrics')
            .select('*')
            .order('captured_at', { ascending: false })
            .limit(Math.max(limit, 500))

        if (youtubeMetricsError && !String(youtubeMetricsError.message || '').includes('youtube_video_metrics')) {
            throw youtubeMetricsError
        }

        const { data: videoLearningRows, error: videoLearningError } = await supabase
            .from('video_learning_snapshots')
            .select('*')
            .order('captured_at', { ascending: false })
            .limit(Math.max(limit, 500))

        if (videoLearningError && !String(videoLearningError.message || '').includes('video_learning_snapshots')) {
            throw videoLearningError
        }

        const rows = events || []
        const manualReviews = rows.filter((row: any) => row.event_type === 'manual_review')
        const ratings = manualReviews
            .map((row: any) => Number(row?.payload?.rating))
            .filter((value: number) => Number.isFinite(value))

        return NextResponse.json({
            status: 'ok',
            stats: {
                source: 'supabase',
                total_events: rows.length,
                total_snapshots: snapshotCount || 0,
                event_counts: countBy(rows, 'event_type'),
                stage_counts: countBy(rows, 'stage'),
                projects: buildProjectRows(rows, limit),
                recent_events: rows.slice(0, limit).map((row: any) => ({
                    id: row.id,
                    project_id: row.local_project_id,
                    project_name: row.project_name,
                    stage: row.stage,
                    event_type: row.event_type,
                    source: row.source,
                    payload: row.payload || {},
                    created_at: row.local_created_at || row.created_at,
                })),
                manual_review_count: manualReviews.length,
                upload_completed_count: rows.filter((row: any) => row.event_type === 'upload_completed').length,
                upload_failed_count: rows.filter((row: any) => row.event_type === 'upload_failed').length,
                qa_hold_count: rows.filter((row: any) => row.event_type === 'qa_hold').length,
                average_rating: ratings.length ? Math.round((ratings.reduce((sum: number, value: number) => sum + value, 0) / ratings.length) * 100) / 100 : null,
            },
            content_generation: feedbackError
                ? { unavailable: true, error: feedbackError.message }
                : summarizeContentFeedback(feedbackRows || []),
            youtube_learning: youtubeMetricsError || videoLearningError
                ? {
                    unavailable: true,
                    error: youtubeMetricsError?.message || videoLearningError?.message,
                }
                : summarizeYoutubeLearning(youtubeMetricsRows || [], videoLearningRows || []),
        })
    } catch (error: any) {
        console.error('Learning stats API error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}

export async function POST(req: Request) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const topicQueueId = String(body.topic_queue_id || '').trim()
        if (!topicQueueId) {
            return NextResponse.json({ error: 'topic_queue_id is required' }, { status: 400 })
        }

        const quality = String(body.outcome_quality || 'neutral').trim()
        const allowedQualities = new Set(['excellent', 'good', 'neutral', 'poor', 'rejected', 'unknown'])
        if (!allowedQualities.has(quality)) {
            return NextResponse.json({ error: 'invalid outcome_quality' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data: topicRow } = await supabase
            .from('topics_queue')
            .select('id, topic, category_id, generated_title, title_candidates, benchmark_analysis, categories(name)')
            .eq('id', topicQueueId)
            .maybeSingle()

        const categories = (topicRow as any)?.categories
        const categoryName = Array.isArray(categories)
            ? categories[0]?.name
            : categories?.name

        const row = {
            topic_queue_id: topicQueueId,
            category_id: String(body.category_id || topicRow?.category_id || ''),
            category_name: body.category_name || categoryName || null,
            feedback_source: 'manual',
            outcome_quality: quality,
            generated_title: String(body.generated_title || topicRow?.generated_title || '').trim() || null,
            production_topic: String(body.production_topic || topicRow?.topic || '').trim() || null,
            title_score: body.title_score == null ? null : Number(body.title_score),
            script_score: body.script_score == null ? null : Number(body.script_score),
            reviewer_email: requester.user.email,
            reviewer_note: String(body.reviewer_note || '').slice(0, 2000) || null,
            metrics: body.metrics && typeof body.metrics === 'object' ? body.metrics : {},
            title_generation: body.title_generation && typeof body.title_generation === 'object'
                ? body.title_generation
                : { title_candidates: topicRow?.title_candidates || [] },
            benchmark_summary: body.benchmark_summary && typeof body.benchmark_summary === 'object'
                ? body.benchmark_summary
                : { benchmark_analysis: topicRow?.benchmark_analysis || null },
            evaluation: body.evaluation && typeof body.evaluation === 'object'
                ? body.evaluation
                : { type: 'manual_review', submitted_at: new Date().toISOString() },
            updated_at: new Date().toISOString(),
        }

        const { data, error } = await supabase
            .from('content_generation_feedback')
            .upsert(row, { onConflict: 'topic_queue_id,feedback_source' })
            .select('*')
            .single()

        if (error) throw error
        await syncContentFeedbackToNotion(data || row)
        return NextResponse.json({ status: 'ok', feedback: data })
    } catch (error: any) {
        console.error('Learning feedback API error:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
