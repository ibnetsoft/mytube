import type { SupabaseClient } from '@supabase/supabase-js'

// [AIR-0230 §2b] Shared by the manual trigger
// (app/api/admin/topics-queue/benchmark-analyze/route.ts POST) and the
// automatic/scheduled trigger (app/api/admin/cron/trigger-benchmark-analyze/route.ts)
// - both create the exact same remote_hermes_queue row shape, per
// docs/AIR_0230_HERMES_BENCHMARK_WORKER_ARCHITECTURE.md §2b ("차이는 오직
// 누가/언제 job row를 insert하는가뿐"). Keeping this in one place means the
// freshness/reuse policy can't drift between the two triggers.

const CONTENT_LANGUAGES = ['ko', 'en', 'ja'] as const
type ContentLanguage = typeof CONTENT_LANGUAGES[number]

function normalizeContentLanguage(value: any): ContentLanguage {
    const lang = String(value || '').trim().toLowerCase()
    return CONTENT_LANGUAGES.includes(lang as ContentLanguage) ? (lang as ContentLanguage) : 'ko'
}

// Mirrors HERMES_TOPIC_INTELLIGENCE_ARCHITECTURE.md §3's "동일 카테고리에
// 유효기간 내 최근 조사가 있으면 새로 부르지 않고 스킵" - a completed
// analysis less than this old is treated as still fresh enough to reuse.
export const BENCHMARK_ANALYSIS_FRESHNESS_HOURS = 24 * 7 // 7 days, design doc's proposed default

export type CategoryForBenchmark = {
    id: string | number
    name?: string | null
    keywords?: string | null
    language?: string | null
    video_type?: string | null
}

export type EnqueueBenchmarkResult =
    | { outcome: 'reused'; job: any }
    | { outcome: 'enqueued'; job: any }
    | { outcome: 'skipped'; reason: string }

export async function enqueueBenchmarkAnalyzeJob(
    supabase: SupabaseClient,
    category: CategoryForBenchmark,
    opts: { force?: boolean } = {}
): Promise<EnqueueBenchmarkResult> {
    const keyword = String(category.keywords || category.name || '').trim()
    if (!keyword) {
        return { outcome: 'skipped', reason: 'no_keyword' }
    }

    if (!opts.force) {
        const freshCutoff = new Date(Date.now() - BENCHMARK_ANALYSIS_FRESHNESS_HOURS * 60 * 60 * 1000).toISOString()
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
            return { outcome: 'reused', job: recent }
        }

        // [AIR-0230 §2b automatic mode] A pending/in-flight job for this
        // category also counts as "don't enqueue another one" - the manual
        // button doesn't need this check (an admin clicking twice on
        // purpose is their call), but a daily cron re-running while a job
        // from yesterday is still queued/running would otherwise pile up
        // duplicate jobs for the same category every single day.
        const { data: inFlight } = await supabase
            .from('remote_hermes_queue')
            .select('id, status')
            .eq('category_id', String(category.id))
            .eq('job_type', 'topic_benchmark_analyze')
            .in('status', ['pending', 'rendering'])
            .limit(1)
            .maybeSingle()

        if (inFlight) {
            return { outcome: 'skipped', reason: 'already_in_flight' }
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

    return { outcome: 'enqueued', job: inserted }
}
