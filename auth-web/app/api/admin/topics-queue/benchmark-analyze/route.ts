import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'

// [AIR-0230] §2b - the web-admin side of the manual trigger for
// topic_benchmark_analyze. This route only enqueues a row in
// public.remote_hermes_queue (migrations/air_0230_hermes_worker_central_protocol.sql,
// still a DRAFT - not applied to any Supabase instance yet) - it does not
// call YouTube/Gemini itself. The actual work happens on the render PC's
// Hermes Worker process once it claims the job over the central protocol
// (worker/hermes_worker.py on branch feat/air-0230-topic-benchmark-analyze).
// See docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2b for the
// manual-vs-automatic trigger decision (both create the same row shape;
// only who/when inserts it differs).

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const CONTENT_LANGUAGES = ['ko', 'en', 'ja'] as const
type ContentLanguage = typeof CONTENT_LANGUAGES[number]

function normalizeContentLanguage(value: any): ContentLanguage {
    const lang = String(value || '').trim().toLowerCase()
    return CONTENT_LANGUAGES.includes(lang as ContentLanguage) ? (lang as ContentLanguage) : 'ko'
}

// [AIR-0230] Cheap freshness reuse, mirrors HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE.md
// §3's "동일 카테고리에 유효기간 내 최근 조사가 있으면 새로 부르지 않고 스킵" - a
// completed analysis less than this old is treated as still fresh enough to
// reuse (POST returns it immediately instead of enqueuing a duplicate job);
// only a genuinely stale/missing analysis or an explicit force refresh
// enqueues new work.
const FRESHNESS_HOURS = 24 * 7 // 7 days, same default the design doc proposes

// POST: 수동 트리거 - 카테고리 하나에 대해 topic_benchmark_analyze job을 큐잉한다.
export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { categoryId, force } = await req.json()
        if (!categoryId) {
            return NextResponse.json({ error: 'Missing categoryId' }, { status: 400 })
        }

        const supabase = getAdmin()

        const { data: category, error: catError } = await supabase
            .from('categories')
            .select('id, name, keywords, language, video_type')
            .eq('id', categoryId)
            .single()

        if (catError || !category) {
            return NextResponse.json({ error: 'Category not found' }, { status: 404 })
        }

        const keyword = String(category.keywords || category.name || '').trim()
        if (!keyword) {
            return NextResponse.json({ error: 'Category has no keywords or name to search with' }, { status: 400 })
        }

        if (!force) {
            const freshCutoff = new Date(Date.now() - FRESHNESS_HOURS * 60 * 60 * 1000).toISOString()
            const { data: recent } = await supabase
                .from('remote_hermes_queue')
                .select('id, status, result_payload, completed_at')
                .eq('category_id', String(category.id))
                .eq('job_type', 'topic_benchmark_analyze')
                .eq('status', 'completed')
                .gte('completed_at', freshCutoff)
                .order('completed_at', { ascending: false })
                .limit(1)
                .maybeSingle()

            if (recent) {
                return NextResponse.json({ success: true, reused: true, job: recent })
            }
        }

        const { data: inserted, error: insertError } = await supabase
            .from('remote_hermes_queue')
            .insert({
                job_type: 'topic_benchmark_analyze',
                category_id: String(category.id),
                payload: {
                    keyword,
                    language: normalizeContentLanguage(category.language),
                    video_type: (category.video_type === 'shorts' ? 'shorts' : 'longform'),
                },
                status: 'pending',
            })
            .select('id, status, created_at')
            .single()

        if (insertError) throw insertError

        return NextResponse.json({ success: true, reused: false, job: inserted })
    } catch (e: any) {
        console.error('Failed to enqueue topic_benchmark_analyze job:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// GET: 카테고리의 가장 최근 topic_benchmark_analyze job 상태 조회 (폴링용).
export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { searchParams } = new URL(req.url)
        const categoryId = searchParams.get('categoryId')
        if (!categoryId) {
            return NextResponse.json({ error: 'Missing categoryId' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('remote_hermes_queue')
            .select('id, status, worker_status, progress, message, result_payload, error_message, created_at, completed_at')
            .eq('category_id', String(categoryId))
            .eq('job_type', 'topic_benchmark_analyze')
            .order('created_at', { ascending: false })
            .limit(1)
            .maybeSingle()

        if (error) throw error

        return NextResponse.json({ job: data || null })
    } catch (e: any) {
        console.error('Failed to fetch topic_benchmark_analyze job status:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
