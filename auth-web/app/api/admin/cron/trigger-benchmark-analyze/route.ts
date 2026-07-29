import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { enqueueBenchmarkAnalyzeJob } from '../../../../../lib/benchmarkAnalyzeTrigger'

export const dynamic = 'force-dynamic'

// [AIR-0230 §2b] Automatic trigger mode - the counterpart to the manual
// "고성과 영상 분석 실행" button
// (app/api/admin/topics-queue/benchmark-analyze/route.ts). Runs once a day
// (vercel.json) and walks every category, enqueueing a topic_benchmark_analyze
// job only for the ones without a fresh-enough completed analysis (or an
// already in-flight one) - see lib/benchmarkAnalyzeTrigger.ts for the shared
// freshness/dedup policy both triggers use.
//
// Same auth pattern as the existing rollup-ai-logs cron
// (app/api/admin/cron/rollup-ai-logs/route.ts): Vercel sends
// `Authorization: Bearer <CRON_SECRET>` automatically when CRON_SECRET is set.

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function GET(req: Request) {
    const authHeader = req.headers.get('authorization')
    if (!process.env.CRON_SECRET || authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
        return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    }

    const supabase = getAdmin()
    const { data: categories, error } = await supabase
        .from('categories')
        .select('id, name, keywords, language, video_type')

    if (error) {
        console.error('[CronTriggerBenchmarkAnalyze] Failed to load categories:', error)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }

    const results: Array<{ category_id: string; category_name: string | null; outcome: string; detail?: string }> = []

    for (const category of categories || []) {
        try {
            const result = await enqueueBenchmarkAnalyzeJob(supabase, category, { force: false })
            results.push({
                category_id: String(category.id),
                category_name: category.name || null,
                outcome: result.outcome,
                ...(result.outcome === 'skipped' ? { detail: result.reason } : {}),
            })
        } catch (e: any) {
            console.error(`[CronTriggerBenchmarkAnalyze] Failed for category ${category.id}:`, e)
            results.push({ category_id: String(category.id), category_name: category.name || null, outcome: 'error', detail: e.message })
        }
    }

    return NextResponse.json({
        success: true,
        categoriesProcessed: results.length,
        enqueued: results.filter(r => r.outcome === 'enqueued').length,
        reused: results.filter(r => r.outcome === 'reused').length,
        skipped: results.filter(r => r.outcome === 'skipped').length,
        errored: results.filter(r => r.outcome === 'error').length,
        results,
    })
}
