import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
    try {
        const { email } = await req.json()
        const cleanEmail = String(email || '').trim().toLowerCase()

        if (!cleanEmail) {
            return NextResponse.json({ success: false, error: '이메일을 입력해주세요.' }, { status: 400 })
        }

        const { data: profile, error } = await supabaseAdmin
            .from('profiles')
            .select('id, email, is_approved, pin_code')
            .eq('email', cleanEmail)
            .maybeSingle()

        if (error) {
            return NextResponse.json({ success: false, error: error.message }, { status: 500 })
        }

        if (!profile) {
            return NextResponse.json({ success: false, error: '등록되지 않은 이메일 계정입니다.' }, { status: 404 })
        }

        if (profile.is_approved === false) {
            return NextResponse.json({ success: false, error: '관리자 승인 대기 중인 계정입니다. 승인 후 이용해주세요.' }, { status: 403 })
        }

        // 임시 비밀번호 생성 (8자 이상, 대소문자/숫자/특수문자 포함)
        const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$'
        let tempPassword = 'Air'
        for (let i = 0; i < 6; i++) {
            tempPassword += chars.charAt(Math.floor(Math.random() * chars.length))
        }
        tempPassword += '!9'

        const { error: updateError } = await supabaseAdmin
            .from('profiles')
            .update({ pin_code: tempPassword })
            .eq('id', profile.id)

        if (updateError) {
            return NextResponse.json({ success: false, error: updateError.message }, { status: 500 })
        }

        return NextResponse.json({
            success: true,
            message: `임시 비밀번호가 발급되었습니다: ${tempPassword}\n(로그인 후 세팅에서 비밀번호를 변경해주세요)`,
            temp_password: tempPassword,
        })
    } catch (err: any) {
        return NextResponse.json({ success: false, error: err?.message || '비밀번호 재설정 실패' }, { status: 500 })
    }
}
