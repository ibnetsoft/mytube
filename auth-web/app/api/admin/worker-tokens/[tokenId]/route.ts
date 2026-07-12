import { NextRequest, NextResponse } from 'next/server'
import { requireSuperAdmin, isAuthResponse } from '../../_auth'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'

// [AIR-0227D Stage 4] Immediate revocation - authenticateWorkerRequest()
// re-reads worker_tokens on every single request (no caching), so a worker
// mid-poll-loop is rejected on its very next call after this runs.
export async function DELETE(req: NextRequest, { params }: { params: { tokenId: string } }) {
    const requester = await requireSuperAdmin(req)
    if (isAuthResponse(requester)) return requester

    const { error } = await supabaseAdmin
        .from('worker_tokens')
        .update({ revoked_at: new Date().toISOString() })
        .eq('token_id', params.tokenId)
        .is('revoked_at', null)

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json({ ok: true, token_id: params.tokenId, revoked: true })
}
