import { NextResponse } from 'next/server'
import { requireStdUser } from '@/lib/stdWeb'
import { supabaseAdmin } from '@/lib/supabaseAdmin'

export const dynamic = 'force-dynamic'
export const maxDuration = 300

export async function PATCH(req: Request, { params }: { params: { projectId: string } }) {
    const auth = await requireStdUser(req)
    if (!auth.ok) return auth.response
    let body: any
    try { body = await req.json() } catch { return NextResponse.json({ success: false, error: 'Invalid JSON' }, { status: 400 }) }
    const field = body?.field
    const value = body?.value
    const numbers = body?.scene_numbers
    if (!['transition_effect', 'image_effect', 'motion_speed'].includes(field)
        || typeof value !== 'string' || value.length > 100 || !Array.isArray(numbers)
        || !numbers.length || numbers.length > 500
        || numbers.some(n => !Number.isInteger(n) || n < 1) || new Set(numbers).size !== numbers.length
        || !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(params.projectId)) {
        return NextResponse.json({ success: false, error: 'Invalid scene effect' }, { status: 400 })
    }
    const { data, error } = await supabaseAdmin.rpc('std_save_scene_effect', {
        p_project_id: params.projectId, p_owner: auth.requester.email,
        p_numbers: numbers, p_field: field, p_value: value,
    })
    if (error) {
        console.error('[scene effect save]', error.message)
        return NextResponse.json({ success: false, error: '씬 효과를 저장하지 못했습니다.' }, { status: 503 })
    }
    if (data?.error) {
        const status = data.error === 'not_found' ? 404 : data.error === 'locked' ? 409 : 400
        return NextResponse.json({ success: false, error: data.error }, { status })
    }
    if (!data?.success) return NextResponse.json({ success: false, error: '씬 효과 저장 결과를 확인하지 못했습니다.' }, { status: 500 })
    return NextResponse.json({ success: true })
}
