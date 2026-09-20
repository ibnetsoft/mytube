import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
)

// POST: 비로그인 사용자의 B2B 도입 신청서 제출
export async function POST(req: Request) {
    try {
        const body = await req.json()
        const {
            company_name,
            brand_name,
            contact_name,
            email,
            phone,
            channel_count,
            estimated_setup_fee,
            estimated_monthly_fee,
            currency,
            notes
        } = body

        if (!company_name || !contact_name || !email || !phone) {
            return NextResponse.json(
                { error: '회사명, 담당자 성함, 이메일, 연락처는 필수 입력 항목입니다.' },
                { status: 400 }
            )
        }

        const count = Math.min(Math.max(Number(channel_count) || 5, 1), 5)
        const setupFee = Number(estimated_setup_fee) || 500
        const monthlyFee = Number(estimated_monthly_fee) || (count * 100)

        const sb = getAdmin()
        const { data, error } = await sb
            .from('tenant_applications')
            .insert({
                company_name: company_name.trim(),
                brand_name: (brand_name || company_name).trim(),
                contact_name: contact_name.trim(),
                email: email.trim().toLowerCase(),
                phone: phone.trim(),
                channel_count: count,
                estimated_setup_fee: setupFee,
                estimated_monthly_fee: monthlyFee,
                currency: currency || 'USD',
                notes: notes ? String(notes).trim() : null,
                status: 'pending'
            })
            .select()
            .single()

        if (error) {
            console.error('Failed to insert tenant application:', error)
            throw error
        }

        return NextResponse.json({
            success: true,
            message: '도입 신청이 정상적으로 접수되었습니다. 담당자 검토 후 연락드리겠습니다.',
            application_id: data.id
        })
    } catch (e: any) {
        console.error('Tenant application submission error:', e)
        return NextResponse.json({ error: e.message || '신청 접수 중 오류가 발생했습니다.' }, { status: 500 })
    }
}
