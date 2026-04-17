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
        const { data: { users }, error: authError } = await supabaseAdmin.auth.admin.listUsers()
        if (authError) throw authError

        const { data: profiles, error: profileError } = await supabaseAdmin
            .from('profiles')
            .select('*')
        
        const enrichedUsers = (users || []).map(user => {
            const profile = (profiles || []).find(p => p.id === user.id) || {}
            const membership = profile.membership || profile.membership_tier || (user.app_metadata?.membership || 'standard')
            
            // [DEBUG] Check if youtube_channel is present
            if (user.user_metadata?.youtube_channel) {
                console.log(`[Users API] User ${user.email} has channel: ${user.user_metadata.youtube_channel}`);
            }
            
            return {
                ...user,
                profile: {
                    token_balance: profile.token_balance || 0,
                    membership_tier: membership,
                    video_limit: profile.video_limit || 50,
                    current_usage: profile.current_usage || 0
                }
            }
        });
        
        console.log(`[Users API] Returning ${enrichedUsers.length} users`);
        return NextResponse.json({ users: enrichedUsers })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
