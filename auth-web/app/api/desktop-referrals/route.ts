import { NextResponse } from 'next/server'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'

export const dynamic = 'force-dynamic'

// [AIR-0225B Phase 1] Desktop app's referral/withdrawal features (세팅 페이지의
// 조직도/수당 내역/USDT 출금 탭 + 구 /referral 대시보드), moved off
// SUPABASE_SERVICE_ROLE_KEY. app/routers/referral.py used to run these queries
// directly against Supabase with the service_role key, which was removed from
// the packaged app - every one of these features has been failing with
// "User ID could not be resolved" since. Ported here 1:1 (the desktop router
// now just proxies), authenticated by the same HMAC session_token scheme as
// desktop-resync/desktop-profile-update.
//
// Note the withdraw action validates balance SERVER-side now - under the old
// design the desktop app did its own balance check and then wrote directly to
// the DB, which a tampered client could bypass entirely.

async function resolveUserId(email: string): Promise<string | null> {
    const { data, error } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data) return null
    return data.id
}

async function actionDashboard(userId: string) {
    const { data: profiles } = await supabaseAdmin
        .from('profiles')
        .select('my_referral_code, referral_code, email')
        .eq('id', userId)
        .maybeSingle()
    const refCode = profiles?.referral_code || profiles?.my_referral_code || ''
    const refLink = refCode ? `https://mytube-ashy-seven.vercel.app?ref=${refCode}` : ''

    const { data: l1 } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .eq('referred_by', userId)
    const l1Ids = (l1 || []).map((r: any) => r.id)

    let l2Count = 0
    if (l1Ids.length) {
        const { count } = await supabaseAdmin
            .from('profiles')
            .select('id', { count: 'exact', head: true })
            .in('referred_by', l1Ids)
        l2Count = count || 0
    }

    // Same RPC the desktop code referenced (its call_rpc helper never actually
    // existed, so this endpoint has been dead even longer than the key removal
    // - fall back to zeros if the RPC isn't deployed).
    let pending = 0
    let approved = 0
    try {
        const { data: kpi, error: kpiError } = await supabaseAdmin.rpc('get_referral_user_kpi', { uid: userId })
        if (!kpiError && kpi) {
            pending = Number(kpi.pendingCommission || 0)
            approved = Number(kpi.approvedCommission || 0)
        }
    } catch {
        // RPC not deployed - keep zeros, matching the old fallback behaviour
    }

    return {
        success: true,
        data: {
            referralCode: refCode,
            referralLink: refLink,
            totalReferrals: l1Ids.length + l2Count,
            level1Count: l1Ids.length,
            level2Count: l2Count,
            activeReferrals: l1Ids.length,
            pendingCommission: pending,
            approvedCommission: approved,
            totalCommission: pending + approved,
        },
    }
}

async function actionTree(userId: string, level?: number) {
    const maxLevel = Number.isInteger(level) ? (level as number) : 2
    const nodes: any[] = []

    const nodeShape = (row: any, lvl: number) => ({
        id: row.id,
        referrer_id: row.referred_by,
        display_name: row.full_name || String(row.email || '').split('@')[0] || 'User',
        email: row.email,
        country: row.referral_country || row.country_code || null,
        created_at: row.created_at,
        total_commission_generated: 0,
        level: lvl,
    })

    const { data: l1 } = await supabaseAdmin
        .from('profiles')
        .select('id, email, full_name, created_at, referred_by, referral_country, country_code')
        .eq('referred_by', userId)
    for (const row of l1 || []) nodes.push(nodeShape(row, 1))

    if (maxLevel >= 2 && (l1 || []).length) {
        const l1Ids = (l1 || []).map((r: any) => r.id)
        const chunkSize = 300
        for (let i = 0; i < l1Ids.length; i += chunkSize) {
            const chunk = l1Ids.slice(i, i + chunkSize)
            const { data: l2 } = await supabaseAdmin
                .from('profiles')
                .select('id, email, full_name, created_at, referred_by, referral_country, country_code')
                .in('referred_by', chunk)
            for (const row of l2 || []) nodes.push(nodeShape(row, 2))
        }
    }

    if (nodes.length) {
        const nodeIds = nodes.map(n => n.id)
        const commissionBySource = new Map<string, number>()
        const chunkSize = 300
        for (let i = 0; i < nodeIds.length; i += chunkSize) {
            const chunk = nodeIds.slice(i, i + chunkSize)
            const { data: rows } = await supabaseAdmin
                .from('referral_commissions')
                .select('source_user_id, commission_tokens')
                .eq('beneficiary_id', userId)
                .in('source_user_id', chunk)
                .neq('commission_type', 'WITHDRAWAL')
            for (const row of rows || []) {
                const prev = commissionBySource.get(row.source_user_id) || 0
                commissionBySource.set(row.source_user_id, prev + (Number(row.commission_tokens) || 0))
            }
        }
        for (const n of nodes) {
            n.total_commission_generated = Math.round((commissionBySource.get(n.id) || 0) * 10000) / 10000
            n.is_active = commissionBySource.has(n.id)
        }
    }

    return { success: true, data: nodes }
}

async function actionTimeline(userId: string, params: any) {
    const page = Number.isInteger(params.page) && params.page > 0 ? params.page : 1
    const limit = Number.isInteger(params.limit) && params.limit > 0 ? Math.min(params.limit, 100) : 10
    const sortBy = ['created_at', 'commission_tokens', 'status'].includes(params.sort_by) ? params.sort_by : 'created_at'
    const sortAsc = params.sort_dir === 'asc'
    const offset = (page - 1) * limit

    let query = supabaseAdmin
        .from('referral_commissions')
        .select('id, commission_type, commission_tokens, status, created_at, paid_at, metadata')
        .eq('beneficiary_id', userId)
        .order(sortBy, { ascending: sortAsc })
        .range(offset, offset + limit - 1)
    if (params.status) query = query.eq('status', String(params.status))
    if (params.type) query = query.eq('commission_type', String(params.type))

    const { data: items, error } = await query
    if (error) throw new Error(error.message)

    const normalised = (items || []).map((item: any) => ({
        id: item.id,
        description: item.commission_type || '수익 발생',
        amount: item.commission_tokens || 0,
        status: String(item.status || 'PENDING').toUpperCase(),
        created_at: item.created_at,
        paid_at: item.paid_at,
    }))

    const hasNext = (items || []).length === limit
    return {
        success: true,
        items: normalised,
        data: normalised,
        has_next: hasNext,
        pagination: { current_page: page, has_next: hasNext, total_records: normalised.length },
    }
}

async function computeWithdrawalInfo(userId: string) {
    const { data: commissions, error } = await supabaseAdmin
        .from('referral_commissions')
        .select('commission_tokens, status, commission_type')
        .eq('beneficiary_id', userId)
    if (error) throw new Error(error.message)

    let totalEarned = 0
    let totalWithdrawn = 0
    let pendingWithdrawal = 0
    for (const c of commissions || []) {
        const amount = Number(c.commission_tokens || 0)
        const status = String(c.status || '').toUpperCase()
        const ctype = String(c.commission_type || '').toUpperCase()
        if (ctype === 'WITHDRAWAL') {
            if (status === 'PENDING') pendingWithdrawal += Math.abs(amount)
            else if (['APPROVED', 'COMPLETED', 'PAID'].includes(status)) totalWithdrawn += Math.abs(amount)
        } else if (['APPROVED', 'COMPLETED', 'PAID'].includes(status)) {
            totalEarned += amount
        }
    }
    const available = Math.max(0, totalEarned - totalWithdrawn - pendingWithdrawal)
    return { totalEarned, totalWithdrawn, pendingWithdrawal, availableBalance: available }
}

async function actionWithdraw(userId: string, params: any) {
    const amount = Number(params.amount)
    const destAddress = String(params.dest_address || '').trim()
    if (!Number.isFinite(amount) || amount <= 0) {
        return { success: false, error: '출금 금액은 0보다 커야 합니다.' }
    }
    if (!destAddress) {
        return { success: false, error: '지갑 주소를 입력해주세요.' }
    }

    const info = await computeWithdrawalInfo(userId)
    if (amount > info.availableBalance) {
        return { success: false, error: '출금 가능 금액을 초과했습니다.' }
    }

    let minWithdrawal = 10
    const { data: minRow } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', 'min_withdrawal_usdt')
        .maybeSingle()
    if (minRow?.value && Number.isFinite(Number(minRow.value))) {
        minWithdrawal = Number(minRow.value)
    }
    if (amount < minWithdrawal) {
        return { success: false, error: `최소 출금 가능 금액은 ${minWithdrawal} USDT 입니다.` }
    }

    // Legacy pattern preserved: negative WITHDRAWAL commission row is the
    // system of record through AIR-0221 Stage 2.
    const { data: legacyRows, error: legacyError } = await supabaseAdmin
        .from('referral_commissions')
        .insert({
            beneficiary_id: userId,
            source_user_id: userId,
            commission_type: 'WITHDRAWAL',
            commission_tokens: -amount,
            status: 'PENDING',
            metadata: { dest_address: destAddress },
        })
        .select('id')
    if (legacyError) {
        console.error('[DesktopReferrals] withdraw legacy insert error:', legacyError.message)
        return { success: false, error: '출금 요청 중 오류가 발생했습니다.' }
    }

    // AIR-0221 Stage 2 dual-write - best-effort, never surfaces to the user.
    try {
        const { error: dwError } = await supabaseAdmin
            .from('referral_withdrawals')
            .insert({
                user_id: userId,
                amount,
                wallet_address: destAddress,
                status: 'REQUESTED',
                metadata: {
                    legacy_source: 'referral_negative_commission',
                    legacy_commission_id: legacyRows?.[0]?.id ?? null,
                },
            })
        if (dwError) {
            console.warn('[DesktopReferrals] Stage2 dual-write failed:', dwError.message)
        }
    } catch (dwErr: any) {
        console.warn('[DesktopReferrals] Stage2 dual-write error:', dwErr?.message)
    }

    return { success: true, message: '출금 신청이 완료되었습니다.' }
}

async function actionWithdrawalHistory(userId: string) {
    const { data: rows, error } = await supabaseAdmin
        .from('referral_withdrawals')
        .select('id, amount, wallet_address, status, tx_hash, created_at')
        .eq('user_id', userId)
        .order('created_at', { ascending: false })
        .limit(100)
    if (error) throw new Error(error.message)

    return {
        success: true,
        data: (rows || []).map((r: any) => ({
            id: r.id,
            created_at: r.created_at,
            wallet_address: r.wallet_address,
            tx_hash: r.tx_hash,
            amount: r.amount,
            status: r.status,
        })),
    }
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { email, session_token, action } = body

        if (!email || !session_token || !action) {
            return NextResponse.json({ success: false, error: 'Missing email, session_token or action' }, { status: 400 })
        }
        const normalizedEmail = String(email)

        if (!(await verifyApprovedDesktopSession(normalizedEmail, String(session_token)))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        const userId = await resolveUserId(normalizedEmail)
        if (!userId) {
            return NextResponse.json({ success: false, error: '등록되지 않은 직원 이메일입니다.' }, { status: 404 })
        }

        switch (String(action)) {
            case 'dashboard':
                return NextResponse.json(await actionDashboard(userId))
            case 'tree':
                return NextResponse.json(await actionTree(userId, body.level))
            case 'timeline':
                return NextResponse.json(await actionTimeline(userId, body))
            case 'withdrawal_info':
                return NextResponse.json({ success: true, data: await computeWithdrawalInfo(userId) })
            case 'withdraw':
                return NextResponse.json(await actionWithdraw(userId, body))
            case 'withdrawal_history':
                return NextResponse.json(await actionWithdrawalHistory(userId))
            default:
                return NextResponse.json({ success: false, error: `Unknown action: ${action}` }, { status: 400 })
        }
    } catch (error: any) {
        console.error('[DesktopReferrals] Error:', error?.message)
        return NextResponse.json({ success: false, error: '동기화 서버 오류' }, { status: 500 })
    }
}
