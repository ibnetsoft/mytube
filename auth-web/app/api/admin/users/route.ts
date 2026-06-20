import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

    if (!supabaseServiceKey) {
        return NextResponse.json({ error: 'Server configuration error' }, { status: 500 })
    }

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: { persistSession: false }
    })

    try {
        // 전체 유저 조회 (페이지네이션 명시)
        const { data: { users }, error: authError } = await supabaseAdmin.auth.admin.listUsers({
            page: 1, perPage: 1000
        })
        if (authError) throw authError

        const { data: profiles } = await supabaseAdmin.from('profiles').select('*')

        const normMembership = (v: string) => ({ standard: 'std', independent: 'pro' })[v] ?? v
        const authUserIds = new Set((users || []).map(u => u.id))

        const enrichedUsers = (users || []).map(user => {
            const profile = (profiles || []).find((p: any) => p.id === user.id) || {}
            const profileData = profile as any;
            const rawMembership = profileData.membership_tier || profileData.membership || (user.app_metadata?.membership || 'std')
            const membership = normMembership(rawMembership)

            console.log(`[Users API] ${user.email} | membership=${membership} | full_name=${user.user_metadata?.full_name}`)
            const userMetadata = {
                ...(user.user_metadata || {}),
                full_name: user.user_metadata?.full_name || profileData.full_name || '',
                contact: user.user_metadata?.contact || profileData.contact || '',
                nationality: user.user_metadata?.nationality || profileData.nationality || '',
            }
            return {
                ...user,
                user_metadata: userMetadata,
                profile: {
                    token_balance: profileData.token_balance || 0,
                    membership_tier: membership,
                    membership: membership,
                    pin_code: profileData.pin_code || '1234',
                    is_approved: profileData.is_approved === true,
                    signup_status: profileData.signup_status || (profileData.is_approved ? 'approved' : 'pending'),
                    signup_source: profileData.signup_source || '',
                    full_name: profileData.full_name || '',
                    contact: profileData.contact || '',
                    nationality: profileData.nationality || '',
                }
            }
        })

        // profiles에만 있고 auth.users에 없는 유저도 포함
        const orphanProfiles = (profiles || []).filter((p: any) => !authUserIds.has(p.id))
        for (const p of orphanProfiles) {
            const membership = normMembership(p.membership_tier || p.membership || 'std')
            console.log(`[Users API] orphan profile ${p.email || p.id} | membership=${membership}`)
            enrichedUsers.push({
                id: p.id,
                email: p.email || '',
                created_at: p.created_at || '',
                email_confirmed_at: null,
                last_sign_in_at: null,
                app_metadata: {},
                user_metadata: {
                    full_name: p.full_name || '',
                    contact: p.contact || '',
                    nationality: p.nationality || '',
                },
                profile: {
                    token_balance: p.token_balance || 0,
                    membership_tier: membership,
                    membership: membership,
                    pin_code: p.pin_code || '1234',
                    is_approved: p.is_approved === true,
                    signup_status: p.signup_status || (p.is_approved ? 'approved' : 'pending'),
                    signup_source: p.signup_source || '',
                    full_name: p.full_name || '',
                    contact: p.contact || '',
                    nationality: p.nationality || '',
                }
            } as any)
        }

        console.log(`[Users API] Returning ${enrichedUsers.length} users (auth=${users?.length ?? 0}, orphan=${orphanProfiles.length})`)
        return NextResponse.json({ users: enrichedUsers }, {
            headers: { 'Cache-Control': 'no-store, no-cache, must-revalidate' }
        })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
