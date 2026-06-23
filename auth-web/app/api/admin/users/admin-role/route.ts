import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const { userId, isAdmin } = await req.json()

        if (!userId) {
            return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data: { user: existingUser }, error: fetchError } = await supabase.auth.admin.getUserById(userId)
        if (fetchError) throw fetchError

        const currentMetadata = existingUser?.app_metadata || {}
        const nextMetadata = {
            ...currentMetadata,
            is_admin: userId === requester.user.id ? currentMetadata.is_admin : false,
            role: isAdmin ? 'sub_admin' : null,
        }

        const { data, error } = await supabase.auth.admin.updateUserById(
            userId,
            { app_metadata: nextMetadata }
        )

        if (error) throw error

        return NextResponse.json({ success: true, data })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
