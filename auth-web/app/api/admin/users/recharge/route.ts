import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function POST(req: Request) {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
    const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY

    if (!supabaseServiceKey) {
        return NextResponse.json({ success: false, error: 'SERVICE_ROLE_KEY is missing' }, { status: 500 })
    }

    const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
        auth: { autoRefreshToken: false, persistSession: false }
    })

    try {
        const { userId, amount, description } = await req.json()

        if (!userId || !amount) {
            return NextResponse.json({ success: false, error: 'Missing parameters' }, { status: 400 })
        }

        const numAmount = Number(amount)
        if (isNaN(numAmount) || numAmount <= 0) {
            return NextResponse.json({ success: false, error: 'Invalid amount' }, { status: 400 })
        }

        console.log(`[Recharge] user=${userId}, amount=${numAmount}`)

        // 1. 현재 잔액 조회 (없으면 null)
        const { data: existingProfile, error: fetchError } = await supabaseAdmin
            .from('profiles')
            .select('token_balance')
            .eq('id', userId)
            .maybeSingle()

        if (fetchError) {
            console.error('[Recharge] Fetch error:', fetchError)
            return NextResponse.json({ success: false, error: `Fetch error: ${fetchError.message}` }, { status: 500 })
        }

        const currentBalance = existingProfile?.token_balance ?? 0
        const newBalance = currentBalance + numAmount
        console.log(`[Recharge] balance: ${currentBalance} → ${newBalance}`)

        if (existingProfile) {
            // 2a. 프로필 있음 → UPDATE (select()로 실제 반영 여부 확인)
            const { data: updatedRows, error: updateError } = await supabaseAdmin
                .from('profiles')
                .update({ token_balance: newBalance })
                .eq('id', userId)
                .select('id, token_balance')

            if (updateError) {
                console.error('[Recharge] Update error:', updateError)
                return NextResponse.json({ success: false, error: `Update error: ${updateError.message}` }, { status: 500 })
            }

            console.log(`[Recharge] Updated rows:`, updatedRows)

            if (!updatedRows || updatedRows.length === 0) {
                console.error('[Recharge] UPDATE matched 0 rows — trying INSERT fallback')
                const { error: insertFallbackError } = await supabaseAdmin
                    .from('profiles')
                    .insert({ id: userId, token_balance: newBalance, membership: 'standard' })
                if (insertFallbackError) {
                    console.error('[Recharge] Insert fallback error:', insertFallbackError)
                    return NextResponse.json({ success: false, error: `Insert fallback error: ${insertFallbackError.message}` }, { status: 500 })
                }
            }
        } else {
            // 2b. 프로필 없음 → INSERT
            const { error: insertError } = await supabaseAdmin
                .from('profiles')
                .insert({ id: userId, token_balance: newBalance, membership: 'standard' })

            if (insertError) {
                console.error('[Recharge] Insert error:', insertError)
                return NextResponse.json({ success: false, error: `Insert error: ${insertError.message}` }, { status: 500 })
            }
        }

        // 3. 트랜잭션 기록 (실패해도 충전은 성공)
        const { error: txError } = await supabaseAdmin
            .from('token_transactions')
            .insert({
                user_id: userId,
                amount: numAmount,
                transaction_type: 'RECHARGE',
                description: description || '관리자 충전'
            })

        if (txError) {
            console.warn('[Recharge] TX log failed (non-fatal):', txError.message)
        }

        console.log(`[Recharge] Done: user=${userId}, new_balance=${newBalance}`)
        return NextResponse.json({ success: true, new_balance: newBalance })

    } catch (error: any) {
        console.error('[Recharge] Unexpected error:', error)
        return NextResponse.json({ success: false, error: error.message || String(error) }, { status: 500 })
    }
}
