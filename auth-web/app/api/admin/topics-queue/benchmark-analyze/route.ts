import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'
import { enqueueBenchmarkAnalyzeJob } from '../../../../../lib/benchmarkAnalyzeTrigger'

// [AIR-0230] §2b - the web-admin side of the manual trigger for
// topic_benchmark_analyze. This route only enqueues a row in
// public.remote_hermes_queue (migrations/air_0230_hermes_worker_central_protocol.sql,
// still a DRAFT - not applied to any Supabase instance yet) - it does not
// call YouTube/Gemini itself. The actual work happens on the render PC's
// Hermes Worker process once it claims the job over the central protocol
// (worker/hermes_worker.py on branch feat/air-0230-topic-benchmark-analyze).
// See docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2b for the
// manual-vs-automatic trigger decision (both create the same row shape via
// lib/benchmarkAnalyzeTrigger.ts; only who/when inserts it differs - the
// automatic side is app/api/admin/cron/trigger-benchmark-analyze/route.ts).

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

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

        const result = await enqueueBenchmarkAnalyzeJob(supabase, category, { force: !!force })

        if (result.outcome === 'skipped') {
            return NextResponse.json({ error: result.reason }, { status: 400 })
        }

        return NextResponse.json({ success: true, reused: result.outcome === 'reused', job: result.job })
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
