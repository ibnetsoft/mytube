import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireAdmin } from '../../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

// POST: 어드민이 답장을 확정 발송한다. AI 초안은 여기서 소비될 뿐 -
// 이 호출 없이는 절대 사용자에게 노출되지 않는다 (요청하신 "어드민 확인
// 후 발송" 요건이 이 엔드포인트 하나로 강제된다).
export async function POST(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { reply } = await req.json()
        const replyText = String(reply || '').trim()
        if (!replyText) {
            return NextResponse.json({ error: 'reply is required' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data, error } = await supabase
            .from('support_messages')
            .update({
                admin_reply: replyText,
                replied_by: requester.user.id,
                replied_at: new Date().toISOString(),
                status: 'ANSWERED',
            })
            .eq('id', params.id)
            .select('id')
            .maybeSingle()

        if (error) throw error
        if (!data) {
            return NextResponse.json({ error: 'Message not found' }, { status: 404 })
        }

        return NextResponse.json({ status: 'ok' })
    } catch (error: any) {
        console.error('[AdminSupport] Reply Error:', error?.message)
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
