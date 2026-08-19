import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

function cleanEmail(value: any) {
    return String(value || '').trim().toLowerCase()
}

function cleanText(value: any) {
    return String(value || '').trim()
}

async function findAuthUserByEmail(email: string) {
    for (let page = 1; page <= 10; page += 1) {
        const { data, error } = await supabaseAdmin.auth.admin.listUsers({ page, perPage: 1000 })
        if (error) throw error
        const found = data.users.find(user => String(user.email || '').toLowerCase() === email)
        if (found) return found
        if (data.users.length < 1000) return null
    }
    return null
}

async function createOrFindAuthUser(input: {
    email: string
    password: string
    metadata: Record<string, any>
}) {
    const { data, error } = await supabaseAdmin.auth.admin.createUser({
        email: input.email,
        password: input.password,
        email_confirm: true,
        user_metadata: input.metadata,
    })
    if (!error && data.user) return data.user

    const message = String(error?.message || '').toLowerCase()
    if (message.includes('already') || message.includes('registered') || message.includes('exists')) {
        const existing = await findAuthUserByEmail(input.email)
        if (existing) {
            await supabaseAdmin.auth.admin.updateUserById(existing.id, {
                password: input.password,
                user_metadata: {
                    ...(existing.user_metadata || {}),
                    ...input.metadata,
                },
            })
            return existing
        }
    }
    throw error || new Error('Auth user creation failed')
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const email = cleanEmail(body?.email)
        const password = cleanText(body?.password)
        const fullName = cleanText(body?.full_name)
        const contact = cleanText(body?.contact)
        const nationality = cleanText(body?.nationality || 'KR')
        const referrer = cleanText(body?.referrer || body?.referral_code || '').toUpperCase()
        const preferredCategoryIds = Array.isArray(body?.preferred_category_ids) ? body.preferred_category_ids : []
        const preferredCategoryNames = Array.isArray(body?.preferred_category_names) ? body.preferred_category_names : []

        if (!email || !password) {
            return NextResponse.json({ success: false, error: '이메일과 비밀번호를 입력해주세요.' }, { status: 400 })
        }
        if (password.length < 6) {
            return NextResponse.json({ success: false, error: '비밀번호는 최소 6자 이상이어야 합니다.' }, { status: 400 })
        }
        if (!fullName || !contact) {
            return NextResponse.json({ success: false, error: '이름과 연락처를 모두 입력해주세요.' }, { status: 400 })
        }

        const { data: existingProfile, error: existingError } = await supabaseAdmin
            .from('profiles')
            .select('*')
            .eq('email', email)
            .maybeSingle()
        if (existingError) throw existingError
        if (existingProfile?.is_approved === true) {
            return NextResponse.json({ success: false, error: '이미 승인된 이메일입니다. 로그인해주세요.' }, { status: 409 })
        }

        const metadata = {
            full_name: fullName,
            contact,
            nationality,
            signup_status: 'pending',
            signup_source: 'std_web',
            referred_by_code: referrer,
            membership: 'std',
            membership_tier: 'std',
        }

        const authUser = await createOrFindAuthUser({ email, password, metadata })
        const now = new Date().toISOString()
        const profilePayload = {
            id: existingProfile?.id || authUser.id,
            email,
            full_name: fullName,
            contact,
            nationality,
            is_approved: false,
            signup_status: 'pending',
            signup_source: 'std_web',
            pin_code: password,
            membership: existingProfile?.membership || 'std',
            membership_tier: existingProfile?.membership_tier || 'std',
            preferred_languages: existingProfile?.preferred_languages || ['ko'],
            preferred_video_length: existingProfile?.preferred_video_length || '',
            preferred_category_ids: preferredCategoryIds.length > 0 ? preferredCategoryIds : (existingProfile?.preferred_category_ids || [2, 3, 4, 5, 6, 7, 8, 9]),
            preferred_category_names: preferredCategoryNames.length > 0 ? preferredCategoryNames : (existingProfile?.preferred_category_names || ['옛날이야기', '경제', '탈북사연', '한국사연', '해외감동', '무협', '노후금융', '황혼19금']),
            referred_by_code: referrer,
            terms_accepted_at: existingProfile?.terms_accepted_at || now,
            privacy_accepted_at: existingProfile?.privacy_accepted_at || now,
        }

        const { error: upsertError } = await supabaseAdmin
            .from('profiles')
            .upsert(profilePayload, { onConflict: 'id' })
        if (upsertError) throw upsertError

        return NextResponse.json({
            success: true,
            status: 'pending',
            message: '가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다.',
        })
    } catch (error: any) {
        console.error('[StdSignup] error:', error?.message)
        return NextResponse.json({ success: false, error: error?.message || '회원가입 실패' }, { status: 500 })
    }
}
