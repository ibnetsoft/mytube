import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 도입 신청서 목록 조회 (슈퍼어드민 전용)
export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const url = new URL(req.url)
        const status = url.searchParams.get('status')

        const sb = getAdmin()
        let query = sb
            .from('tenant_applications')
            .select('*')
            .order('created_at', { ascending: false })

        if (status && status !== 'all') {
            query = query.eq('status', status)
        }

        const { data: applications, error } = await query

        if (error) throw error

        return NextResponse.json({
            applications: applications || [],
            total: applications?.length || 0
        })
    } catch (e: any) {
        console.error('Failed to list tenant applications:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
