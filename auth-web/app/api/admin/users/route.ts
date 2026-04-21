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
            return {
                ...user,
                profile: {
                    token_balance: profileData.token_balance || 0,
                    membership_tier: membership,
                    membership: membership,
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
                user_metadata: { full_name: p.full_name || '' },
                profile: {
                    token_balance: p.token_balance || 0,
                    membership_tier: membership,
                    membership: membership,
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
