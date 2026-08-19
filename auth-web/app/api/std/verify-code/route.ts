import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

declare global {
    var _stdVerifyCodes: Map<string, { code: string; expiresAt: number }> | undefined
}

export async function POST(req: Request) {
    try {
        const { email, code } = await req.json()
        const cleanEmail = String(email || '').trim().toLowerCase()
        const cleanCode = String(code || '').trim()

        if (!cleanEmail || !cleanCode) {
            return NextResponse.json({ success: false, error: '이메일과 인증코드를 모두 입력해주세요.' }, { status: 400 })
        }

        const entry = globalThis._stdVerifyCodes?.get(cleanEmail)
        if (!entry) {
            return NextResponse.json({ success: false, error: '인증 코드를 먼저 발송해주세요.' }, { status: 400 })
        }

        if (Date.now() > entry.expiresAt) {
            globalThis._stdVerifyCodes?.delete(cleanEmail)
            return NextResponse.json({ success: false, error: '인증 코드가 만료되었습니다. 다시 발송해주세요.' }, { status: 400 })
        }

        if (entry.code !== cleanCode) {
            return NextResponse.json({ success: false, error: '인증 코드가 일치하지 않습니다.' }, { status: 400 })
        }

        // 인증 성공 후 제거
        globalThis._stdVerifyCodes?.delete(cleanEmail)

        return NextResponse.json({
            success: true,
            verified: true,
            message: '이메일 인증이 완료되었습니다.',
        })
    } catch (err: any) {
        return NextResponse.json({ success: false, error: err?.message || '인증 확인 실패' }, { status: 500 })
    }
}
