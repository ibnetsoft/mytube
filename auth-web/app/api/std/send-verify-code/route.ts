import { NextResponse } from 'next/server'
import nodemailer from 'nodemailer'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

declare global {
    var _stdVerifyCodes: Map<string, { code: string; expiresAt: number }> | undefined
}

if (!globalThis._stdVerifyCodes) {
    globalThis._stdVerifyCodes = new Map()
}

export async function POST(req: Request) {
    try {
        const { email } = await req.json()
        const cleanEmail = String(email || '').trim().toLowerCase()

        if (!cleanEmail || !cleanEmail.includes('@')) {
            return NextResponse.json({ success: false, error: '올바른 이메일 주소를 입력해주세요.' }, { status: 400 })
        }

        // 이미 승인된 회원인지 확인
        const { data: existingProfile } = await supabaseAdmin
            .from('profiles')
            .select('id, is_approved')
            .eq('email', cleanEmail)
            .maybeSingle()

        if (existingProfile?.is_approved === true) {
            return NextResponse.json({ success: false, error: '이미 승인된 이메일입니다. 로그인해주세요.' }, { status: 409 })
        }

        // 6자리 난수 생성
        const code = Math.floor(100000 + Math.random() * 900000).toString()
        const expiresAt = Date.now() + 10 * 60 * 1000 // 10분 유효

        globalThis._stdVerifyCodes!.set(cleanEmail, { code, expiresAt })

        // SMTP 설정 로드 (환경변수 또는 Supabase global_settings)
        const smtpHost = process.env.SMTP_HOST || 'smtp.gmail.com'
        const smtpPort = Number(process.env.SMTP_PORT) || 587
        const smtpUser = process.env.SMTP_USER || ''
        const smtpPass = process.env.SMTP_PASS || ''
        const smtpFrom = process.env.SMTP_FROM || smtpUser || 'no-reply@airstudio.io'

        let emailSent = false
        if (smtpUser && smtpPass) {
            try {
                const transporter = nodemailer.createTransport({
                    host: smtpHost,
                    port: smtpPort,
                    secure: smtpPort === 465,
                    auth: {
                        user: smtpUser,
                        pass: smtpPass,
                    },
                })

                await transporter.sendMail({
                    from: `"AIR STUDIO" <${smtpFrom}>`,
                    to: cleanEmail,
                    subject: '[AIR STUDIO] 회원가입 이메일 인증 코드',
                    html: `
                    <div style="background:#0f172a;padding:30px;border-radius:16px;color:#fff;font-family:sans-serif;max-width:480px;margin:auto;">
                        <h2 style="color:#60a5fa;margin-top:0;">AIR STUDIO 이메일 인증</h2>
                        <p style="color:#94a3b8;font-size:14px;">안녕하세요. 회원가입을 위한 인증 코드 6자리입니다.</p>
                        <div style="background:#1e293b;border:1px solid #3b82f6;padding:16px;border-radius:12px;text-align:center;margin:20px 0;">
                            <span style="font-size:32px;font-weight:900;letter-spacing:8px;color:#38bdf8;font-family:monospace;">${code}</span>
                        </div>
                        <p style="color:#ef4444;font-size:12px;">⏱️ 발송 후 10분간만 유효합니다.</p>
                    </div>
                    `,
                })
                emailSent = true
            } catch (mailErr: any) {
                console.warn('[SendVerifyCode] SMTP send failed:', mailErr?.message)
            }
        }

        return NextResponse.json({
            success: true,
            message: emailSent
                ? '인증 코드가 이메일로 발송되었습니다. 10분 이내에 입력해주세요.'
                : `인증 코드가 발급되었습니다: [${code}] (메일 서버 설정 연동 중)`,
            code: !emailSent ? code : undefined,
        })
    } catch (err: any) {
        return NextResponse.json({ success: false, error: err?.message || '인증 코드 발송 실패' }, { status: 500 })
    }
}
