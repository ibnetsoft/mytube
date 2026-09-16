import { NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { signDesktopSessionToken } from '@/lib/desktopSession'
import { ensureStage1WalletForUser, publicStage1Wallet } from '@/lib/walletStage1'

export const dynamic = 'force-dynamic'

function getAuthClient() {
    return createClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        { auth: { persistSession: false, autoRefreshToken: false } }
    )
}

function isApproved(profile: any) {
    return profile?.is_approved === true || String(profile?.is_approved).toLowerCase() === 'true'
}

function isStdMember(profile: any) {
    const membership = String(profile?.membership_tier || profile?.membership || 'std').toLowerCase()
    return ['std', 'standard'].includes(membership)
}

function userPayload(profile: any) {
    return {
        id: profile.id,
        email: profile.email,
        full_name: profile.full_name || '',
        membership: profile.membership_tier || profile.membership || 'std',
        signup_status: profile.signup_status || (isApproved(profile) ? 'approved' : 'pending'),
    }
}

async function fetchProfileByEmail(email: string) {
    try {
        const { data, error } = await supabaseAdmin
            .from('profiles')
            .select('*')
            .ilike('email', email.trim())
            .maybeSingle()
        if (error) {
            console.warn('[StdLogin] fetchProfileByEmail error:', error.message)
            throw new Error('로그인 DB에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.')
        }
        return data
    } catch {
        throw new Error('로그인 DB에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    }
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const normalizedEmail = String(body?.email || '').trim().toLowerCase()
        const inputPassword = String(body?.password || '').trim()

        if (!normalizedEmail || !inputPassword) {
            return NextResponse.json({ success: false, error: '이메일과 비밀번호를 입력해주세요.' }, { status: 400 })
        }

        const profile = await fetchProfileByEmail(normalizedEmail)
        const pinCode = String(profile?.pin_code || '').trim()

        // 1. PIN 코드 또는 비밀번호 일치 확인
        if (profile && pinCode && (pinCode === inputPassword || pinCode === inputPassword.toLowerCase())) {
            const wallet = await ensureStage1WalletForUser(profile.id)
            return NextResponse.json({
                success: true,
                auth_type: 'pin',
                session_token: signDesktopSessionToken(normalizedEmail),
                user: userPayload(profile),
                wallet: publicStage1Wallet(wallet),
                wallet_address: wallet?.address || '',
            })
        }

        const fallbackProfile = {
            id: 'worker-' + Buffer.from(normalizedEmail).toString('hex').slice(0, 12),
            email: normalizedEmail,
            full_name: normalizedEmail.split('@')[0] || 'STD 작업자',
            membership_tier: 'std',
            is_approved: true,
            signup_status: 'approved',
        }

        let authData: any = { session: null, user: null }
        let authError: any = null
        try {
            const authResult = await getAuthClient().auth.signInWithPassword({
                email: normalizedEmail,
                password: inputPassword,
            })
            authData = authResult.data
            authError = authResult.error
        } catch {
            throw new Error('인증 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.')
        }

        if (!authError && authData?.session?.access_token && authData?.user?.email) {
            let resolvedProfile = profile
            if (!resolvedProfile) {
                let data = null
                try {
                    const profileResult = await supabaseAdmin
                        .from('profiles')
                        .select('*')
                        .or(`id.eq.${authData.user.id},email.eq.${normalizedEmail}`)
                        .maybeSingle()
                    data = profileResult.data
                } catch {
                    data = null
                }
                resolvedProfile = data
            }

            const wallet = resolvedProfile?.id ? await ensureStage1WalletForUser(resolvedProfile.id) : null

            return NextResponse.json({
                success: true,
                auth_type: 'desktop',
                session_token: signDesktopSessionToken(normalizedEmail),
                user: userPayload(resolvedProfile || fallbackProfile),
                wallet: publicStage1Wallet(wallet),
                wallet_address: wallet?.address || '',
            })
        }

        return NextResponse.json({
            success: false,
            error: authError?.status >= 500
                ? '인증 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.'
                : '이메일 또는 비밀번호를 확인해 주세요.',
        }, { status: authError?.status >= 500 ? 503 : 401 })
    } catch (error: any) {
        console.error('[StdLogin] error:', error?.message)
        return NextResponse.json({ success: false, error: '로그인 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.' }, { status: 503 })
    }
}
