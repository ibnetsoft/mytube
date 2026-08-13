import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { processSettlement } from '../../../lib/settlement'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// POST: 로컬(데스크톱) 앱에서 AI 작업 로그를 받아 Supabase에 저장하고,
// 사용량 누적 + 추천인 커미션 정산을 수행한다.
//
// [AIR-0225B] 인증: 예전에는 body의 userId(UUID)만 믿고 저장/정산했다 -
// UUID만 알면 누구나 임의 유저 명의로 가짜 로그를 넣어 커미션(→USDT 출금)을
// 부풀리거나 사용량을 조작할 수 있는 구멍이었다. 이제 desktop-referrals /
// desktop-topics-bridge와 동일하게 email + HMAC session_token을 검증하고,
// user_id는 클라이언트가 보낸 값이 아니라 session의 email로부터 서버가
// 직접 해석한다(클라이언트 제공 userId는 신뢰하지 않음).
async function resolveUserId(email: string): Promise<string | null> {
    const { data, error } = await getAdmin()
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data) return null
    return data.id
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const {
            email, session_token,
            task_type, model_id, provider, status,
            prompt_summary, error_msg, elapsed_time,
            input_tokens, output_tokens, balance_after, thinking_tokens,
            worker_email,
        } = body

        if (!email || !session_token) {
            return NextResponse.json({ error: 'missing_email_or_session_token' }, { status: 401 })
        }
        if (!(await verifyApprovedDesktopSession(String(email), String(session_token)))) {
            return NextResponse.json({ error: 'invalid_or_expired_session' }, { status: 401 })
        }

        const supabaseAdmin = getAdmin()

        // user_id는 검증된 session의 email로부터만 해석한다.
        const userId = await resolveUserId(String(email))
        if (!userId) return NextResponse.json({ error: 'Invalid user' }, { status: 401 })

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
                balance_after: balance_after,
                // [AIR-0230] "누가" API를 많이 썼는지 웹어드민에서 집계할 수 있도록
                // 프로젝트에 태깅된 담당 직원 이메일을 함께 저장한다.
                worker_email: worker_email || null,
            })
            .select('id')
            .maybeSingle()

        if (error) throw error

        // [Usage Metering] 작업 성공 시 사용량 누적(RECHARGE/BILLING 유형 제외).
        // 잔액을 깎던(deduct_tokens) 방식을 폐기하고 record_token_usage로 사용량만
        // 쌓는다 - 토큰 잔액이 부족하다는 이유로 플랫폼 이용이 막히는 일은 없다.
        const NO_METER_TYPES = ['RECHARGE', 'BILLING']
        const totalTokens = (input_tokens || 0) + (output_tokens || 0) + (thinking_tokens || 0)
        if (totalTokens > 0 && (status === 'success' || status === 'done') && !NO_METER_TYPES.includes((task_type || '').toUpperCase())) {
            const { error: meterError } = await supabaseAdmin.rpc('record_token_usage', {
                p_user_id: userId,
                p_amount: totalTokens,
                p_description: `${task_type} (${model_id})`
            })
            if (meterError) {
                console.error(`[Logs] Usage metering failed for ${userId}: ${meterError.message}`)
            } else {
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
