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
            full_name: profile.full_name || '',
            membership: profile.membership_tier || profile.membership || 'std',
            preferred_languages: profile.preferred_languages || ['ko'],
            preferred_video_length: profile.preferred_video_length || '',
            preferred_category_ids: profile.preferred_category_ids || [],
        },
    })
}
