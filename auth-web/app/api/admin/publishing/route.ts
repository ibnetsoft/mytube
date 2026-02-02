
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
    console.log('--- Admin Publishing GET Started ---')
    try {
        const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
        const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

        if (!supabaseUrl || !supabaseServiceKey) {
            console.error("Missing Supabase env vars:", { url: !!supabaseUrl, key: !!supabaseServiceKey })
            return NextResponse.json({
                error: "Server configuration error (env vars missing)",
                details: { url: !!supabaseUrl, key: !!supabaseServiceKey }
            }, { status: 500 })
        }

        const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
            auth: {
                autoRefreshToken: false,
                persistSession: false
            }
        })

        // 1. Fetch requests (Essential)
        console.log('Fetching publishing_requests...')
        const { data: requests, error: reqError } = await supabaseAdmin
            .from('publishing_requests')
            .select('*')
            .order('created_at', { ascending: false })

        if (reqError) {
            console.error('Database query error:', reqError)
            return NextResponse.json({ error: `Database error: ${reqError.message}` }, { status: 500 })
        }

        // 2. Fetch users (Optional/Safe)
        console.log('Fetching user list for emails...')
        let emailMap = new Map()
        try {
            const { data: userData, error: userError } = await supabaseAdmin.auth.admin.listUsers()
            if (userError) {
                console.warn("Could not list users via Admin SDK:", userError.message)
            } else if (userData?.users) {
                userData.users.forEach(u => emailMap.set(u.id, u.email))
            }
        } catch (uErr: any) {
            console.warn("User list fetch crashed:", uErr.message)
        }

        // 3. Transform data
        const requestsWithUrls = (requests || []).map(req => {
            const email = emailMap.get(req.user_id) || 'Unknown User'

            // Construct base object
            const enriched = {
                ...req,
                profiles: { email } // Match frontend expectation
            }

            // Cloud URL handling
            if (req.metadata?.isCloud && req.video_url) {
                return {
                    ...enriched,
                    video_url: `${supabaseUrl}/storage/v1/object/public/videos/${req.video_url}`
                }
            }
            return enriched
        })

        console.log(`Admin GET Success: Returning ${requestsWithUrls.length} items`)
        return NextResponse.json({ requests: requestsWithUrls })

    } catch (err: any) {
        console.error("Unexpected Admin API Error:", err)
        return NextResponse.json({ error: err.message || "Unknown server error" }, { status: 500 })
    }
}

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey)

    try {
        const { requestId, status } = await req.json()

        if (!requestId || !status) {
            return NextResponse.json({ error: 'Missing requestId or status' }, { status: 400 })
        }

        const { data, error } = await supabaseAdmin
            .from('publishing_requests')
            .update({ status })
            .eq('id', requestId)
            .select()

        if (error) throw error

        return NextResponse.json({ success: true, request: data[0] })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
