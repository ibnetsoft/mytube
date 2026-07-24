import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// [무음 실패 로그 방지] 데스크톱 앱이 세션 토큰을 못 가진 상태(구버전 로그인,
// 만료 등)에서는 기존 /api/logs가 401로 거절했고, 데스크톱은 그 실패를 콘솔에만
// 찍고 조용히 버렸다 - 웹어드민 에러 로그 패널에 아무 것도 안 남아 유저가 TTS
// 실패를 신고해도 원인을 추적할 방법이 없었다(실제로 발생: worker_email이 이
// 테이블에 한 번도 안 찍힌 케이스 확인됨).
//
// 이 엔드포인트는 그 최후 수단이다. /api/logs와 달리 세션 토큰을 검증하지
// 않는다 - 대신 정산(processSettlement)과 사용량 집계(record_token_usage)를
// 완전히 건너뛰어서, 이메일만 아는 제3자가 토큰/커미션을 조작할 방법이 없게
// 만든다. status는 항상 'failed'로 고정 - 성공 이벤트를 위조해봤자 아무 금전적
// 이득도 없지만, 굳이 그 표면적을 열어둘 이유가 없다.
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
        const { email, task_type, model_id, provider, error_msg, worker_email } = body

        if (!email || typeof email !== 'string') {
            return NextResponse.json({ error: 'missing_email' }, { status: 400 })
        }

        const userId = await resolveUserId(email)
        if (!userId) return NextResponse.json({ error: 'unknown_email' }, { status: 404 })

        const { error } = await getAdmin()
            .from('ai_logs')
            .insert({
                user_id: userId,
                task_type: task_type || 'unknown',
                model_id: model_id || null,
                provider: provider || null,
                status: 'failed',
                prompt_summary: '[no active session - unauthenticated report]',
                error_msg: String(error_msg || '').slice(0, 500),
                elapsed_time: 0,
                input_tokens: 0,
                output_tokens: 0,
                thinking_tokens: 0,
                balance_after: null,
                worker_email: worker_email || email,
            })

        if (error) throw error
        return NextResponse.json({ success: true })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
