import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 특정 테넌트 정보 + 사용자 목록
export async function GET(req: Request, { params }: { params: { key: string } }) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const sb = getAdmin()
        const tenantKey = params.key

        // 테넌트 정보 조회
        const { data: tenant, error: tenantError } = await sb
            .from('tenant_configs')
            .select('*')
            .eq('tenant_key', tenantKey)
            .single()

        if (tenantError || !tenant) {
            return NextResponse.json({ error: 'Tenant not found' }, { status: 404 })
        }

        // 테넌트 사용자 목록 조회
        const { data: users, error: usersError } = await sb
            .from('tenant_users')
            .select('*,profiles(email,full_name)')
            .eq('tenant_key', tenantKey)
            .order('created_at', { ascending: false })

        return NextResponse.json({
            tenant,
            users: users || []
        })
    } catch (e: any) {
        console.error('Failed to get tenant:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// PATCH: 테넌트 설정 업데이트 (수수료 등)
export async function PATCH(req: Request, { params }: { params: { key: string } }) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const { commission_percent, min_commission_usd, status, brand_name, primary_color, watermark_enabled } = body

        const sb = getAdmin()
        const tenantKey = params.key

        const updateData: any = { updated_at: new Date().toISOString() }
        if (commission_percent !== undefined) updateData.commission_percent = commission_percent
        if (min_commission_usd !== undefined) updateData.min_commission_usd = min_commission_usd
        if (status !== undefined) updateData.status = status
        if (brand_name !== undefined) updateData.brand_name = brand_name
        if (primary_color !== undefined) updateData.primary_color = primary_color
        if (watermark_enabled !== undefined) updateData.watermark_enabled = watermark_enabled

        const { data, error } = await sb
            .from('tenant_configs')
            .update(updateData)
            .eq('tenant_key', tenantKey)
            .select()
            .single()

        if (error || !data) {
            return NextResponse.json({ error: 'Failed to update tenant' }, { status: 400 })
        }

        return NextResponse.json({ success: true, tenant: data })
    } catch (e: any) {
        console.error('Failed to update tenant:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// DELETE: 테넌트 삭제
export async function DELETE(req: Request, { params }: { params: { key: string } }) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const sb = getAdmin()
        const tenantKey = params.key

        if (tenantKey === 'default') {
            return NextResponse.json({ error: 'Cannot delete default tenant' }, { status: 400 })
        }

        const { error } = await sb
            .from('tenant_configs')
            .delete()
            .eq('tenant_key', tenantKey)

        if (error) throw error

        return NextResponse.json({ success: true })
    } catch (e: any) {
        console.error('Failed to delete tenant:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}