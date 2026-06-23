import { createClient, type User } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const SUPER_ADMIN_EMAIL = 'ejsh0519@naver.com'

export type AdminCheck = {
    user: User
    isSuperAdmin: boolean
    isSubAdmin: boolean
    isAdmin: boolean
}

const getAuthClient = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { auth: { persistSession: false, autoRefreshToken: false } }
)

export async function getRequester(req: Request): Promise<AdminCheck | null> {
    const authHeader = req.headers.get('authorization') || ''
    const token = authHeader.toLowerCase().startsWith('bearer ')
        ? authHeader.slice(7).trim()
        : ''

    if (!token) return null

    const { data, error } = await getAuthClient().auth.getUser(token)
    const user = data.user
    if (error || !user?.email) return null

    const isSuperAdmin = user.email.toLowerCase() === SUPER_ADMIN_EMAIL.toLowerCase()
    const isSubAdmin = user.app_metadata?.role === 'sub_admin'

    return {
        user,
        isSuperAdmin,
        isSubAdmin,
        isAdmin: isSuperAdmin || isSubAdmin,
    }
}

export async function requireAdmin(req: Request): Promise<AdminCheck | NextResponse> {
    const requester = await getRequester(req)
    if (!requester?.isAdmin) {
        return NextResponse.json({ error: 'Admin access required' }, { status: 403 })
    }
    return requester
}

export async function requireSuperAdmin(req: Request): Promise<AdminCheck | NextResponse> {
    const requester = await getRequester(req)
    if (!requester?.isSuperAdmin) {
        return NextResponse.json({ error: 'Super admin access required' }, { status: 403 })
    }
    return requester
}

export function isAuthResponse(value: AdminCheck | NextResponse): value is NextResponse {
    return value instanceof NextResponse
}
