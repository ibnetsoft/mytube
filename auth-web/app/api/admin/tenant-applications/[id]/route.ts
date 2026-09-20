import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// POST: 신청서 승인 및 테넌트 자동 생성
export async function POST(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const sb = getAdmin()
        const applicationId = params.id
        const body = await req.json().catch(() => ({}))

        // 1. 신청서 조회
        const { data: application, error: appError } = await sb
            .from('tenant_applications')
            .select('*')
            .eq('id', applicationId)
            .single()

        if (appError || !application) {
            return NextResponse.json({ error: '신청서를 찾을 수 없습니다.' }, { status: 404 })
        }

        if (application.status === 'approved') {
            return NextResponse.json({ error: '이미 승인된 신청서입니다.', tenant_key: application.tenant_key }, { status: 400 })
        }

        // 2. 테넌트 키 결정
        let targetKey = body.tenant_key
            ? body.tenant_key.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '')
            : application.company_name.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/^-+|-+$/g, '')

        if (!targetKey) {
            targetKey = `tenant-${Date.now().toString(36)}`
        }

        // 중복 시 타임스탬프 추가
        const { data: existingTenant } = await sb
            .from('tenant_configs')
            .select('tenant_key')
            .eq('tenant_key', targetKey)
            .single()

        if (existingTenant) {
            targetKey = `${targetKey}-${Math.floor(1000 + Math.random() * 9000)}`
        }

        const maxChannels = body.max_channels !== undefined ? Number(body.max_channels) : (application.channel_count || 5)
        const setupFee = body.setup_fee_usd !== undefined ? Number(body.setup_fee_usd) : (application.estimated_setup_fee || 500)
        const pricePerChannel = body.price_per_channel_usd !== undefined ? Number(body.price_per_channel_usd) : 100
        const monthlyFee = pricePerChannel * maxChannels
        const currency = body.currency || application.currency || 'USD'

        // 3. tenant_configs에 신규 테넌트 생성
        const { data: newTenant, error: createError } = await sb
            .from('tenant_configs')
            .insert({
                tenant_key: targetKey,
                tenant_name: application.company_name,
                brand_name: application.brand_name || application.company_name,
                setup_fee_usd: setupFee,
                price_per_channel_usd: pricePerChannel,
                max_channels: maxChannels,
                monthly_fee_usd: monthlyFee,
                currency: currency,
                commission_percent: 0,
                min_commission_usd: 0,
                license_tier: body.license_tier || 'business',
                status: 'active'
            })
            .select()
            .single()

        if (createError) {
            console.error('Failed to auto-create tenant on approval:', createError)
            throw createError
        }

        // 4. 신청서 승인 완료 처리
        const { error: updateAppError } = await sb
            .from('tenant_applications')
            .update({
                status: 'approved',
                tenant_key: targetKey,
                reviewed_at: new Date().toISOString(),
                reviewed_by: requester.user.id
            })
            .eq('id', applicationId)

        if (updateAppError) {
            console.error('Failed to update application status:', updateAppError)
        }

        return NextResponse.json({
            success: true,
            message: `테넌트 [${targetKey}]가 성공적으로 자동 생성 및 승인되었습니다.`,
            tenant: newTenant,
            tenant_key: targetKey
        })
    } catch (e: any) {
        console.error('Error approving application:', e)
        return NextResponse.json({ error: e.message || '승인 처리 실패' }, { status: 500 })
    }
}

// PATCH: 신청서 상태 변경 (예: 반려 rejected)
export async function PATCH(req: Request, { params }: { params: { id: string } }) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const sb = getAdmin()
        const applicationId = params.id
        const body = await req.json()
        const { status, notes } = body

        if (!status || !['pending', 'approved', 'rejected'].includes(status)) {
            return NextResponse.json({ error: '유효한 상태값이 필요합니다 (pending, approved, rejected)' }, { status: 400 })
        }

        const updatePayload: any = {
            status,
            reviewed_at: new Date().toISOString(),
            reviewed_by: requester.user.id
        }
        if (notes !== undefined) updatePayload.notes = notes

        const { data, error } = await sb
            .from('tenant_applications')
            .update(updatePayload)
            .eq('id', applicationId)
            .select()
            .single()

        if (error) throw error

        return NextResponse.json({ success: true, application: data })
    } catch (e: any) {
        console.error('Error updating application:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}
