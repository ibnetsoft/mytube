import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const SUPER_ADMIN = 'ejsh0519@naver.com'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function POST(req: Request) {
    try {
        const { userId, isAdmin } = await req.json()

        if (!userId) {
            return NextResponse.json({ error: 'Missing userId' }, { status: 400 })
        }

        const supabase = getAdmin()

        const { data, error } = await supabase.auth.admin.updateUserById(
            userId,
            { app_metadata: { is_admin: isAdmin } }
        )

        if (error) throw error

        return NextResponse.json({ success: true, data })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
