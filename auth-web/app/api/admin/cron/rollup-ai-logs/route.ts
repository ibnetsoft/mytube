import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

// [AIR-0231] ai_logs 보존 정책 - 90일 지난 원본 row를 (날짜, 직원, 모델,
// task_type) 단위로 ai_logs_daily_summary에 집계해두고 삭제한다. 단순
// TTL 삭제가 아니라 "요약 후 삭제"인 이유: 원본이 지워진 뒤에도 월별/직원별
// 장기 비용 추이 비교가 가능해야 하기 때문 (DashboardContent.tsx 현황요약
// 탭의 byWorker/byModel 집계와 같은 계산 로직을 여기서도 재사용한다).
//
// Vercel Cron이 매일 호출한다(vercel.json). 한 번 실행에 최대 MAX_DAYS_PER_RUN
// 일(day)치만 처리해서 - 특정 날짜의 (직원 x 모델 x task_type) 조합 수는
// 많아야 수십 개라 하루치 처리는 가볍지만, 최초 실행 시 90일 백로그를 전부
// 한 번에 처리하려 하면 함수 타임아웃/메모리 위험이 있다. 매일 조금씩 따라
// 잡는 방식.

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

const RETENTION_DAYS = 90
const MAX_DAYS_PER_RUN = 7
const MAX_ROWS_PER_DAY = 20000

function calcRowCost(row: any, pricingMap: Record<string, any>): number {
    const price = pricingMap[row.model_id]
    const inputT = row.input_tokens || 0
    const outputT = row.output_tokens || 0
    const thinkingT = row.thinking_tokens || 0
    if (price && (price.input_per_1k || price.output_per_1k)) {
        const thinkingRate = price.thinking_per_1k ?? price.output_per_1k ?? 0
        return (inputT / 1000) * (price.input_per_1k || 0)
            + (outputT / 1000) * (price.output_per_1k || 0)
            + (thinkingT / 1000) * thinkingRate
    }
    // 현황요약 탭과 동일한 flat-rate 폴백 (단가 미설정 모델)
    return (inputT + outputT + thinkingT) * 0.00002
}

// worker_email/model_id/task_type이 NULL일 수 있어 .eq()로는 매칭이 안 된다
// (SQL NULL = NULL은 항상 false) - null-safe하게 조회한다.
function matchNullable(query: any, column: string, value: string | null) {
    return value === null ? query.is(column, null) : query.eq(column, value)
}

export async function GET(req: Request) {
    // Vercel Cron 인증: CRON_SECRET 환경변수를 설정해두면 Vercel이 자동으로
    // Authorization: Bearer <CRON_SECRET> 헤더를 붙여 호출한다.
    const authHeader = req.headers.get('authorization')
    if (!process.env.CRON_SECRET || authHeader !== `Bearer ${process.env.CRON_SECRET}`) {
        return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
    }

    // ?dry_run=true면 집계 결과만 계산해서 보여주고 실제 upsert/delete는
    // 건너뛴다 - 처음 배포 후 실제 삭제 전에 결과가 말이 되는지 눈으로
    // 확인하는 용도. 운영 cron 호출(vercel.json)은 이 파라미터를 안 붙인다.
    const dryRun = new URL(req.url).searchParams.get('dry_run') === 'true'

    const sb = getAdmin()
    const cutoff = new Date()
    cutoff.setUTCDate(cutoff.getUTCDate() - RETENTION_DAYS)
    const cutoffISO = cutoff.toISOString()

    let pricingMap: Record<string, any> = {}
    try {
        const { data } = await sb.from('global_settings').select('value').eq('key', 'model_pricing').maybeSingle()
        if (data?.value) pricingMap = JSON.parse(data.value)
    } catch {
        // 파싱 실패 시 flat-rate 폴백으로 계속 진행
    }

    const daysProcessed: string[] = []
    const groupsPreview: any[] = []
    let totalRolledUp = 0

    for (let i = 0; i < MAX_DAYS_PER_RUN; i++) {
        const { data: oldestRow } = await sb
            .from('ai_logs')
            .select('created_at')
            .lt('created_at', cutoffISO)
            .order('created_at', { ascending: true })
            .limit(1)
            .maybeSingle()

        if (!oldestRow) break // 처리할 백로그가 더 없음

        const dayStart = new Date(oldestRow.created_at)
        dayStart.setUTCHours(0, 0, 0, 0)
        const dayEnd = new Date(dayStart)
        dayEnd.setUTCDate(dayEnd.getUTCDate() + 1)
        const logDate = dayStart.toISOString().slice(0, 10)

        const { data: rows, error: fetchError } = await sb
            .from('ai_logs')
            .select('id, worker_email, model_id, provider, task_type, status, input_tokens, output_tokens, thinking_tokens')
            .gte('created_at', dayStart.toISOString())
            .lt('created_at', dayEnd.toISOString())
            .limit(MAX_ROWS_PER_DAY)

        if (fetchError) {
            console.error('[RollupAiLogs] fetch error:', fetchError)
            break
        }
        if (!rows || !rows.length) break

        type Group = {
            worker_email: string | null; model_id: string | null; provider: string | null; task_type: string | null
            count: number; success_count: number
            input_tokens: number; output_tokens: number; thinking_tokens: number
            cost_estimate: number
        }
        const groups: Record<string, Group> = {}
        for (const row of rows) {
            const key = `${row.worker_email || ''}::${row.model_id || ''}::${row.task_type || ''}`
            if (!groups[key]) {
                groups[key] = {
                    worker_email: row.worker_email || null,
                    model_id: row.model_id || null,
                    provider: row.provider || null,
                    task_type: row.task_type || null,
                    count: 0, success_count: 0,
                    input_tokens: 0, output_tokens: 0, thinking_tokens: 0,
                    cost_estimate: 0,
                }
            }
            const g = groups[key]
            g.count += 1
            const status = (row.status || '').toLowerCase()
            if (status === 'success' || status === 'done') g.success_count += 1
            g.input_tokens += row.input_tokens || 0
            g.output_tokens += row.output_tokens || 0
            g.thinking_tokens += row.thinking_tokens || 0
            g.cost_estimate += calcRowCost(row, pricingMap)
        }

        for (const g of Object.values(groups)) {
            let existingQuery = sb.from('ai_logs_daily_summary').select('*').eq('log_date', logDate)
            if (dryRun) {
                groupsPreview.push({ log_date: logDate, ...g })
                continue
            }

            existingQuery = matchNullable(existingQuery, 'worker_email', g.worker_email)
            existingQuery = matchNullable(existingQuery, 'model_id', g.model_id)
            existingQuery = matchNullable(existingQuery, 'task_type', g.task_type)
            const { data: existing } = await existingQuery.maybeSingle()

            if (existing) {
                await sb.from('ai_logs_daily_summary').update({
                    count: existing.count + g.count,
                    success_count: existing.success_count + g.success_count,
                    input_tokens: existing.input_tokens + g.input_tokens,
                    output_tokens: existing.output_tokens + g.output_tokens,
                    thinking_tokens: existing.thinking_tokens + g.thinking_tokens,
                    cost_estimate: Number(existing.cost_estimate) + g.cost_estimate,
                }).eq('id', existing.id)
            } else {
                await sb.from('ai_logs_daily_summary').insert({
                    log_date: logDate,
                    worker_email: g.worker_email,
                    model_id: g.model_id,
                    provider: g.provider,
                    task_type: g.task_type,
                    count: g.count,
                    success_count: g.success_count,
                    input_tokens: g.input_tokens,
                    output_tokens: g.output_tokens,
                    thinking_tokens: g.thinking_tokens,
                    cost_estimate: g.cost_estimate,
                })
            }
        }

        totalRolledUp += rows.length
        daysProcessed.push(logDate)

        if (dryRun) break // dry-run은 삭제를 안 하므로 "가장 오래된 날짜"가 안 바뀐다 - 미리보기 1일치만 보여주고 끝낸다.

        const ids = rows.map(r => r.id)
        const { error: deleteError } = await sb.from('ai_logs').delete().in('id', ids)
        if (deleteError) {
            console.error('[RollupAiLogs] delete error:', deleteError)
            break
        }

        // 그 날짜의 row가 MAX_ROWS_PER_DAY보다 많았다면 아직 남아있으므로
        // 다음 루프에서 같은 날짜를 다시 집어 이어서 처리한다.
        if (rows.length >= MAX_ROWS_PER_DAY) break
    }

    return NextResponse.json({
        success: true,
        dryRun,
        retentionDays: RETENTION_DAYS,
        daysProcessed,
        totalRolledUp,
        ...(dryRun ? { groupsPreview } : {}),
    })
}
