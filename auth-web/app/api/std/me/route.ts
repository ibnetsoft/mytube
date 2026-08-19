import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response

    const { user, profile, email } = auth.requester
    return NextResponse.json({
        success: true,
        user: {
            id: user.id,
            email,
            full_name: profile.full_name || email.split('@')[0] || 'STD 작업자',
            nationality: profile.nationality || '대한민국',
            contact: profile.contact || '',
            referral_code: profile.referral_code || profile.my_referral_code || '',
            membership: profile.membership_tier || profile.membership || 'std',
            preferred_languages: profile.preferred_languages || ['ko'],
            preferred_video_length: profile.preferred_video_length || '',
            preferred_category_ids: profile.preferred_category_ids || [],
            preferred_category_names: profile.preferred_category_names || [],
            token_balance: profile.token_balance ?? 0,
            usdt_balance: profile.usdt_balance ?? 0,
        },
    })
}
