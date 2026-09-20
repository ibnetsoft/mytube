import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'
import { isAuthResponse, requireSuperAdmin } from '../../_auth'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// GET: 모든 테넌트 목록 조회
export async function GET(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const sb = getAdmin()
        const { data: tenants, error } = await sb
            .from('tenant_configs')
            .select('*')
            .order('created_at', { ascending: false })

        if (error) throw error

        // 각 테넌트의 사용자 수 조회
        const tenantKeys = (tenants || []).map(t => t.tenant_key)
        const { data: tenantUsers, error: usersError } = await sb
            .from('tenant_users')
            .select('tenant_key')
            .in('tenant_key', tenantKeys)

        if (!usersError && tenantUsers) {
            const userCountMap = new Map<string, number>()
            tenantUsers.forEach(u => {
                const count = userCountMap.get(u.tenant_key) || 0
                userCountMap.set(u.tenant_key, count + 1)
            })
            tenants?.forEach((t: any) => {
                t.user_count = userCountMap.get(t.tenant_key) || 0
            })
        }

        return NextResponse.json({ tenants: tenants || [] })
    } catch (e: any) {
        console.error('Failed to get tenants:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}

// POST: 새 테넌트 생성
export async function POST(req: Request) {
    try {
        const requester = await requireSuperAdmin(req)
        if (isAuthResponse(requester)) return requester

        const body = await req.json()
        const {
            tenant_key,
            tenant_name,
            brand_name,
            commission_percent,
            min_commission_usd,
            license_tier,
            setup_fee_usd,
            price_per_channel_usd,
            max_channels,
            currency
        } = body

        if (!tenant_key || !tenant_name) {
            return NextResponse.json({ error: 'tenant_key and tenant_name are required' }, { status: 400 })
        }

        const sb = getAdmin()

        // 중복 체크
        const { data: existing } = await sb
            .from('tenant_configs')
            .select('tenant_key')
            .eq('tenant_key', tenant_key)
            .single()

        if (existing) {
            return NextResponse.json({ error: 'Tenant key already exists' }, { status: 400 })
        }

        const parsedMaxChannels = max_channels !== undefined ? Number(max_channels) : 5
        const parsedPricePerChannel = price_per_channel_usd !== undefined ? Number(price_per_channel_usd) : 0
        const calculatedMonthlyFee = parsedPricePerChannel * parsedMaxChannels

        const { data, error } = await sb
            .from('tenant_configs')
            .insert({
                tenant_key,
                tenant_name,
                brand_name: brand_name || tenant_name,
                commission_percent: commission_percent !== undefined ? Number(commission_percent) : 10,
                min_commission_usd: min_commission_usd !== undefined ? Number(min_commission_usd) : 0,
                license_tier: license_tier || 'standard',
                setup_fee_usd: setup_fee_usd !== undefined ? Number(setup_fee_usd) : 0,
                price_per_channel_usd: parsedPricePerChannel,
                max_channels: parsedMaxChannels,
                monthly_fee_usd: calculatedMonthlyFee,
                currency: currency || 'USD',
                status: 'active'
            })
            .select()
            .single()

        if (error) throw error

        return NextResponse.json({ success: true, tenant: data })
    } catch (e: any) {
        console.error('Failed to create tenant:', e)
        return NextResponse.json({ error: e.message }, { status: 500 })
    }
}