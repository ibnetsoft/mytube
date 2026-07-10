import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { processSettlement } from '../../../lib/settlement'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// POST: 로컬 앱에서 로그 전송 받아 Supabase 저장
export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { userId, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time, input_tokens, output_tokens, balance_after, thinking_tokens } = body

        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        const supabaseAdmin = getAdmin()

        // userId가 실제 존재하는 유저인지 확인
        const { data: { user }, error: userErr } = await supabaseAdmin.auth.admin.getUserById(userId)
        if (userErr || !user) return NextResponse.json({ error: 'Invalid userId' }, { status: 401 })

        const { data: logRow, error } = await supabaseAdmin
            .from('ai_logs')
            .insert({
                user_id: userId,
                task_type,
                model_id,
                provider,
                status,
                prompt_summary: (prompt_summary || '').slice(0, 500),
                error_msg: (error_msg || '').slice(0, 500),
                elapsed_time: elapsed_time || 0,
                input_tokens: input_tokens || 0,
                output_tokens: output_tokens || 0,
                thinking_tokens: thinking_tokens || 0,
                balance_after: balance_after
            })
            .select('id')
            .maybeSingle()

        if (error) throw error

        // [Credit System] 작업 성공 시 토큰 차감 (RECHARGE/BILLING 유형은 차감 제외)
        const NO_DEDUCT_TYPES = ['RECHARGE', 'BILLING']
        const totalTokens = (input_tokens || 0) + (output_tokens || 0) + (thinking_tokens || 0)
        if (totalTokens > 0 && (status === 'success' || status === 'done') && !NO_DEDUCT_TYPES.includes((task_type || '').toUpperCase())) {
            const { data: deductResult, error: deductError } = await supabaseAdmin.rpc('deduct_tokens', {
                p_user_id: userId,
                p_amount: totalTokens,
                p_description: `${task_type} (${model_id})`
            })
            if (deductError) {
                console.error(`[Logs] Token deduction failed for ${userId}: ${deductError.message}`)
            } else {
                console.log(`[Logs] Deducted ${totalTokens} tokens from ${userId}, result:`, deductResult)

                // [Referral Commission] 실사용(영상 작업) 기반 추천인 1·2단계 커미션 지급.
                // 토큰 사용량을 그대로 커미션 산정 기준액(base_tokens)으로 사용 -
                // 예: 4토큰 사용 -> 기준액 4 -> 설정된 요율만큼 커미션 계산.
                // ai_logs row id를 source_tx_id로 사용해 중복 지급 방지(processSettlement 내장 체크).
                // await 필수: Vercel 서버리스 함수는 응답 반환 직후 실행이 끊길 수 있어서,
                // fire-and-forget(.catch만 걸고 await 안 함)으로는 이 작업이 완료된다는
                // 보장이 없다 - 실제로 커미션이 생성되지 않는 문제로 확인됨.
                if (logRow?.id) {
                    try {
                        await processSettlement(supabaseAdmin, userId, totalTokens, logRow.id)
                    } catch (err) {
                        console.error(`[Logs] Settlement worker error for ${userId}:`, err)
                    }
                }
            }
        }

        return NextResponse.json({ success: true })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
