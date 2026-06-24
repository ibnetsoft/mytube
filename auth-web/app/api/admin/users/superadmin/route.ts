import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// PATCH: 사용자 슈퍼어드민 권한 설정
export async function PATCH(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const { userId, isSuperAdmin } = body

        if (!userId || typeof isSuperAdmin !== 'boolean') {
            return NextResponse.json({ error: 'Invalid parameters' }, { status: 400 })
        }

        const sb = getAdmin()

        // profiles 업데이트
        const { data, error } = await sb
            .from('profiles')
            .update({ is_superadmin: isSuperAdmin })
            .eq('id', userId)
            .select()
            .single()

        if (error) throw error

        // auth.users 메타데이터도 업데이트
        const authRes = await fetch(`${process.env.NEXT_PUBLIC_SUPABASE_URL}/auth/v1/admin/users/${userId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'apikey': process.env.SUPABASE_SERVICE_ROLE_KEY!,
                'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY!}`
            },
            body: JSON.stringify({
                user_metadata: {
                    is_superadmin: isSuperAdmin
                }
            })
        })

        if (!authRes.ok) {
            console.warn('Failed to update auth user metadata, but profile updated successfully')
        }

        return NextResponse.json({ success: true, data })
    } catch (e: any) {
        console.error('Failed to update superadmin status:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}