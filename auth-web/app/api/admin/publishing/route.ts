
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: {
            autoRefreshToken: false,
            persistSession: false
        }
    })

    try {
        // Fetch publishing requests with user emails
        // Note: This assumes a 'publishing_requests' table exists
        const { data, error } = await supabaseAdmin
            .from('publishing_requests')
            .select('*, profiles(email)')
            .order('created_at', { ascending: false })

        if (error) {
            // If table doesn't exist yet, return empty list to avoid crash
            if (error.code === '42P01') {
                return NextResponse.json({ requests: [] })
            }
            throw error
        }

        return NextResponse.json({ requests: data })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
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
