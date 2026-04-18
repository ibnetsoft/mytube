import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// POST: 로컬 앱에서 로그 전송 받아 Supabase 저장
export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { userId, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time, input_tokens, output_tokens } = body

        if (!userId) return NextResponse.json({ error: 'Missing userId' }, { status: 400 })

        // userId가 실제 존재하는 유저인지 확인
        const { data: { user }, error: userErr } = await getAdmin().auth.admin.getUserById(userId)
        if (userErr || !user) return NextResponse.json({ error: 'Invalid userId' }, { status: 401 })

        const { error } = await getAdmin()
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
            })

        if (error) throw error

        // [Credit System] 작업 성공 시 토큰 차감 진행
        const totalTokens = (input_tokens || 0) + (output_tokens || 0)
        if (totalTokens > 0 && (status === 'success' || status === 'done')) {
            const { data: deductResult, error: deductError } = await getAdmin().rpc('deduct_tokens', {
                p_user_id: userId,
                p_amount: totalTokens,
                p_description: `${task_type} (${model_id})`
            })
            if (deductError) {
                console.error(`[Logs] Token deduction failed for ${userId}: ${deductError.message}`)
            } else {
                console.log(`[Logs] Deducted ${totalTokens} tokens from ${userId}, result:`, deductResult)
            }
        }

        return NextResponse.json({ success: true })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
