import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0228 Stage 2] Returns the caller's currently ACTIVE badges. Used by
// the desktop app's sidebar indicator and the settings page status card.

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function GET(req: Request) {
    try {
        const { searchParams } = new URL(req.url)
        const email = searchParams.get('email') || ''
        const sessionToken = searchParams.get('session_token') || ''

        if (!email || !sessionToken) {
            return NextResponse.json({ status: 'error', detail: 'missing_email_or_session_token' }, { status: 401 })
        }
        if (!(await verifyApprovedDesktopSession(email, sessionToken))) {
            return NextResponse.json({ status: 'error', detail: 'invalid_or_expired_session' }, { status: 401 })
        }

        const supabase = getAdmin()
        const { data: profile } = await supabase
            .from('profiles')
            .select('id')
            .eq('email', email)
            .maybeSingle()
        if (!profile) {
            return NextResponse.json({ status: 'error', detail: 'profile_not_found' }, { status: 404 })
        }

        const { data, error } = await supabase
            .from('user_badges')
            .select('badge_code, granted_at, expires_at')
            .eq('user_id', profile.id)
            .eq('status', 'ACTIVE')
        if (error) throw error

        return NextResponse.json({ status: 'ok', badges: data || [] })
    } catch (error: any) {
        console.error('[BadgesMe] Error:', error?.message)
        return NextResponse.json({ status: 'error', detail: 'internal_error' }, { status: 500 })
    }
}
