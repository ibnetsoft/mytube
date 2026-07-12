
import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { requireSuperAdmin, isAuthResponse } from '../../_auth'

// [AIR-0227D-VALIDATION Stage 1/2 - security hotfix] This route could
// ban/unban ANY user account with zero authentication - found while
// auditing for the same "no admin auth check" pattern as
// /api/admin/render-queue. No caller currently exists anywhere in the live
// codebase (grepped the whole repo - only a stale local patch file
// references it), so adding the gate carries no compatibility risk. Also
// removes the anon-key service_role fallback (Stage 2) by using the shared,
// fail-closed `supabaseAdmin` client instead of constructing its own.
export async function POST(req: Request) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    try {
        const { userId, ban } = await req.json()

        if (userId === undefined || ban === undefined) {
            return NextResponse.json({ error: 'Missing userId or ban status' }, { status: 400 })
        }

        // app_metadata에 banned 상태를 저장하여 프론트 및 미들웨어에서 체크할 수 있게 함
        const { data, error } = await supabaseAdmin.auth.admin.updateUserById(
            userId,
            { app_metadata: { banned: ban } }
        )

        if (error) throw error

        console.warn(`[admin-audit] action=user.${ban ? 'ban' : 'unban'} requester=${requester.user.email || 'unknown'} detail=${JSON.stringify({ userId })}`)

        return NextResponse.json({ success: true, user: data.user })
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
