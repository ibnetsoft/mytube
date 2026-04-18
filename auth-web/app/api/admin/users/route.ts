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

        const enrichedUsers = (users || []).map(user => {
            const profile = (profiles || []).find((p: any) => p.id === user.id) || {}
            const membership = (profile as any).membership || (profile as any).membership_tier || (user.app_metadata?.membership || 'standard')
            console.log(`[Users API] ${user.email} | full_name=${user.user_metadata?.full_name} | nationality=${user.user_metadata?.nationality} | contact=${user.user_metadata?.contact}`)
            return {
                ...user,
                profile: {
                    token_balance: (profile as any).token_balance || 0,
                    membership_tier: membership,
                }
            }
        })

        console.log(`[Users API] Returning ${enrichedUsers.length} users`)
        return NextResponse.json({ users: enrichedUsers })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
