import { NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export async function PATCH(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const id = String(body?.id || '').trim()
        const hidden = body?.hidden === true
        if (!id) {
            return NextResponse.json({ error: 'Missing topic id' }, { status: 400 })
        }

        const supabase = getAdmin()
        const { data: existing, error: existingError } = await supabase
            .from('topics_queue')
            .select('id, status, progress_payload')
            .eq('id', id)
            .single()

        if (existingError || !existing) {
            return NextResponse.json({ error: 'Topic not found' }, { status: 404 })
        }

        const currentStatus = String(existing.status || '')
        if (hidden && !['pending', 'assigned', 'excluded'].includes(currentStatus)) {
            return NextResponse.json({ error: 'Only active topics can be hidden' }, { status: 400 })
        }

        const currentProgress = existing.progress_payload && typeof existing.progress_payload === 'object'
            ? existing.progress_payload
            : {}
        const previousStatus = currentStatus === 'excluded'
            ? String(currentProgress.admin_hidden_previous_status || 'pending')
            : currentStatus
        const progressPayload = { ...currentProgress }

        if (hidden) {
            progressPayload.admin_hidden = true
            progressPayload.admin_hidden_at = new Date().toISOString()
            progressPayload.admin_hidden_previous_status = previousStatus
        } else {
            delete progressPayload.admin_hidden
            delete progressPayload.admin_hidden_at
            delete progressPayload.admin_hidden_previous_status
            delete progressPayload.worker_delivery_excluded
            delete progressPayload.worker_delivery_excluded_at
        }

        const restoredStatus = ['pending', 'assigned'].includes(previousStatus) ? previousStatus : 'pending'
        const { data: topic, error: updateError } = await supabase
            .from('topics_queue')
            .update({
                status: hidden ? 'excluded' : restoredStatus,
                progress_payload: progressPayload,
            })
            .eq('id', id)
            .select('id, status, progress_payload')
            .single()

        if (updateError) throw updateError

        return NextResponse.json({ success: true, hidden, topic })
    } catch (e: any) {
        console.error('Failed to change topic visibility:', e)
        return NextResponse.json({ error: e?.message || String(e) }, { status: 500 })
    }
}
