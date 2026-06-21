import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

    if (!supabaseServiceKey) {
        return NextResponse.json({ error: 'Server configuration error' }, { status: 500 })
    }

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: { persistSession: false }
    })

    // 페이지네이션 파라미터. 미지정 시 전체 유저를 자동으로 끝까지 순회한다.
    const { searchParams } = new URL(req.url)
    const pageParam = searchParams.get('page')
    const perPageParam = searchParams.get('perPage')
    const perPage = Math.max(1, Math.min(1000, Number.parseInt(perPageParam ?? '1000', 10) || 1000))
    const requestedPage = pageParam != null ? Math.max(1, Number.parseInt(pageParam, 10) || 1) : null

    try {
        // 전체 유저 조회. page가 주어지면 해당 페이지만, 아니면 1000명 초과 환경을 위해 끝까지 순회한다.
        let users: any[] = []
        if (requestedPage != null) {
            const { data, error: authError } = await supabaseAdmin.auth.admin.listUsers({
                page: requestedPage, perPage
            })
            if (authError) throw authError
            users = data.users || []
        } else {
            for (let page = 1; ; page++) {
                const { data, error: authError } = await supabaseAdmin.auth.admin.listUsers({
                    page, perPage
                })
                if (authError) throw authError
                const batch = data.users || []
                users = users.concat(batch)
                if (batch.length < perPage) break
            }
        }
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
                    usdt_balance: profileData.usdt_balance || 0,
                    wallet_address: profileData.wallet_address || '',
                    membership_tier: membership,
                    membership: membership,
                    pin_code: profileData.pin_code || '1234',
                    is_approved: profileData.is_approved === true,
                    signup_status: profileData.signup_status || (profileData.is_approved ? 'approved' : 'pending'),
                    signup_source: profileData.signup_source || '',
                    full_name: profileData.full_name || '',
                    contact: profileData.contact || '',
                    nationality: profileData.nationality || '',
                    preferred_category_ids: profileData.preferred_category_ids || [],
                    preferred_category_names: profileData.preferred_category_names || [],
                    preferred_video_length: profileData.preferred_video_length || '',
                    persona_name: profileData.persona_name || '',
                    persona_style: profileData.persona_style || '',
                    persona_description: profileData.persona_description || '',
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
                    usdt_balance: p.usdt_balance || 0,
                    wallet_address: p.wallet_address || '',
                    membership_tier: membership,
                    membership: membership,
                    pin_code: p.pin_code || '1234',
                    is_approved: p.is_approved === true,
                    signup_status: p.signup_status || (p.is_approved ? 'approved' : 'pending'),
                    signup_source: p.signup_source || '',
                    full_name: p.full_name || '',
                    contact: p.contact || '',
                    nationality: p.nationality || '',
                    preferred_category_ids: p.preferred_category_ids || [],
                    preferred_category_names: p.preferred_category_names || [],
                    preferred_video_length: p.preferred_video_length || '',
                    persona_name: p.persona_name || '',
                    persona_style: p.persona_style || '',
                    persona_description: p.persona_description || '',
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
