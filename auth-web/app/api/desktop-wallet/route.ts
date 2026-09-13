import { NextResponse } from 'next/server'
import { Contract, Interface, JsonRpcProvider, formatUnits, id, zeroPadValue } from 'ethers'
import { supabaseAdmin } from '@/lib/supabaseAdmin'
import { verifyApprovedDesktopSession } from '@/lib/desktopSession'
import { ensureStage1WalletForUser, publicStage1Wallet } from '@/lib/walletStage1'

export const dynamic = 'force-dynamic'

const EVM_ADDRESS_RE = /^0x[a-fA-F0-9]{40}$/
const EVM_TX_RE = /^0x[a-fA-F0-9]{64}$/
const DEFAULT_AIR_CONTRACT = '0xC0d415c55576596437e865533Dd2730293999EDf'
const DECIMAL_SCALE = 18n
const DECIMAL_FACTOR = 10n ** DECIMAL_SCALE
const TRANSFER_TOPIC = id('Transfer(address,address,uint256)')
const ERC20_ABI = [
    'function decimals() view returns (uint8)',
    'event Transfer(address indexed from, address indexed to, uint256 value)',
]

type WalletAsset = 'AIR' | 'USDT'

type WalletSettings = {
    rpcUrls: string[]
    chainId: number
    airContractAddress: string
    depositsEnabled: boolean
    swapsEnabled: boolean
    withdrawalsEnabled: boolean
    swapFeePercent: string
    airToUsdtRate: string
    usdtToAirRate: string
    minAirWithdrawal: string
    minUsdtWithdrawal: string
    airWithdrawalFee: string
    usdtWithdrawalFee: string
}

function normalizeBool(value: unknown, fallback = true): boolean {
    if (value === undefined || value === null || value === '') return fallback
    return ['1', 'true', 'yes', 'on', 'enabled'].includes(String(value).trim().toLowerCase())
}

function normalizeChainId(value: unknown): number {
    const parsed = Number.parseInt(String(value || ''), 10)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1
}

function uniqueNonEmpty(values: unknown[]): string[] {
    const seen = new Set<string>()
    const result: string[] = []
    for (const value of values) {
        const text = String(value || '').trim()
        if (!text || seen.has(text)) continue
        seen.add(text)
        result.push(text)
    }
    return result
}

function decimalToUnits(value: unknown): bigint {
    const raw = String(value ?? '0').trim()
    if (!raw || raw === '.') return 0n
    const negative = raw.startsWith('-')
    const unsigned = negative ? raw.slice(1) : raw
    if (!/^\d*(\.\d*)?$/.test(unsigned)) throw new Error(`invalid_decimal:${raw}`)
    const [wholeRaw, fracRaw = ''] = unsigned.split('.')
    const whole = BigInt(wholeRaw || '0') * DECIMAL_FACTOR
    const frac = BigInt((fracRaw.slice(0, Number(DECIMAL_SCALE)).padEnd(Number(DECIMAL_SCALE), '0')) || '0')
    const units = whole + frac
    return negative ? -units : units
}

function unitsToDecimal(units: bigint): string {
    const negative = units < 0n
    const abs = negative ? -units : units
    const whole = abs / DECIMAL_FACTOR
    const frac = abs % DECIMAL_FACTOR
    const fracText = frac.toString().padStart(Number(DECIMAL_SCALE), '0').replace(/0+$/, '')
    return `${negative ? '-' : ''}${whole.toString()}${fracText ? `.${fracText}` : ''}`
}

function addDecimal(a: unknown, b: unknown): string {
    return unitsToDecimal(decimalToUnits(a) + decimalToUnits(b))
}

function subDecimal(a: unknown, b: unknown): string {
    return unitsToDecimal(decimalToUnits(a) - decimalToUnits(b))
}

function mulDecimal(a: unknown, b: unknown): string {
    return unitsToDecimal((decimalToUnits(a) * decimalToUnits(b)) / DECIMAL_FACTOR)
}

function divDecimal(a: unknown, b: unknown): string {
    const denominator = decimalToUnits(b)
    if (denominator <= 0n) throw new Error('division_by_zero')
    return unitsToDecimal((decimalToUnits(a) * DECIMAL_FACTOR) / denominator)
}

function gtDecimal(a: unknown, b: unknown): boolean {
    return decimalToUnits(a) > decimalToUnits(b)
}

function gteDecimal(a: unknown, b: unknown): boolean {
    return decimalToUnits(a) >= decimalToUnits(b)
}

function positiveDecimal(value: unknown): boolean {
    return decimalToUnits(value) > 0n
}

async function resolveUserId(email: string): Promise<string | null> {
    const { data, error } = await supabaseAdmin
        .from('profiles')
        .select('id')
        .eq('email', email)
        .maybeSingle()
    if (error || !data?.id) return null
    return data.id
}

async function loadWalletSettings(): Promise<WalletSettings> {
    const keys = [
        'wallet_erc20_rpc_url',
        'wallet_erc20_rpc_fallback_url_1',
        'wallet_erc20_rpc_fallback_url_2',
        'wallet_erc20_rpc_fallback_url_3',
        'wallet_chain_id',
        'wallet_air_contract_address',
        'wallet_deposits_enabled',
        'wallet_swaps_enabled',
        'wallet_withdrawals_enabled',
        'wallet_swap_fee_percent',
        'wallet_air_to_usdt_rate',
        'wallet_usdt_to_air_rate',
        'wallet_min_air_withdrawal',
        'wallet_min_usdt_withdrawal',
        'wallet_air_withdrawal_fee',
        'wallet_usdt_withdrawal_fee',
    ]
    const { data } = await supabaseAdmin
        .from('global_settings')
        .select('key,value')
        .in('key', keys)

    const rows = new Map((data || []).map((row: any) => [String(row.key), String(row.value || '')]))
    return {
        rpcUrls: uniqueNonEmpty([
            rows.get('wallet_erc20_rpc_url'),
            rows.get('wallet_erc20_rpc_fallback_url_1'),
            rows.get('wallet_erc20_rpc_fallback_url_2'),
            rows.get('wallet_erc20_rpc_fallback_url_3'),
        ]),
        chainId: normalizeChainId(rows.get('wallet_chain_id')),
        airContractAddress: rows.get('wallet_air_contract_address') || DEFAULT_AIR_CONTRACT,
        depositsEnabled: normalizeBool(rows.get('wallet_deposits_enabled'), true),
        swapsEnabled: normalizeBool(rows.get('wallet_swaps_enabled'), true),
        withdrawalsEnabled: normalizeBool(rows.get('wallet_withdrawals_enabled'), true),
        swapFeePercent: rows.get('wallet_swap_fee_percent') || '0',
        airToUsdtRate: rows.get('wallet_air_to_usdt_rate') || '0',
        usdtToAirRate: rows.get('wallet_usdt_to_air_rate') || '0',
        minAirWithdrawal: rows.get('wallet_min_air_withdrawal') || '0',
        minUsdtWithdrawal: rows.get('wallet_min_usdt_withdrawal') || '10',
        airWithdrawalFee: rows.get('wallet_air_withdrawal_fee') || '0',
        usdtWithdrawalFee: rows.get('wallet_usdt_withdrawal_fee') || '0',
    }
}

async function withRpcProvider<T>(settings: WalletSettings, work: (provider: JsonRpcProvider) => Promise<T>): Promise<T> {
    let lastError: any = null
    for (const url of settings.rpcUrls) {
        try {
            const provider = new JsonRpcProvider(url, settings.chainId)
            return await work(provider)
        } catch (error: any) {
            lastError = error
            console.warn('[DesktopWallet] RPC fallback failed:', error?.message || error)
        }
    }
    throw new Error(lastError?.message || 'RPC URL이 설정되지 않았거나 연결할 수 없습니다.')
}

async function ensureBalanceRows(userId: string) {
    const { error } = await supabaseAdmin
        .from('wallet_balances')
        .upsert([
            { user_id: userId, asset: 'AIR', available_amount: '0', locked_amount: '0' },
            { user_id: userId, asset: 'USDT', available_amount: '0', locked_amount: '0' },
        ], { onConflict: 'user_id,asset' })
    if (error) throw error
}

async function getBalances(userId: string) {
    await ensureBalanceRows(userId)
    const { data, error } = await supabaseAdmin
        .from('wallet_balances')
        .select('asset,available_amount,locked_amount')
        .eq('user_id', userId)
    if (error) throw error
    const result: Record<WalletAsset, { available: string; locked: string }> = {
        AIR: { available: '0', locked: '0' },
        USDT: { available: '0', locked: '0' },
    }
    for (const row of data || []) {
        const asset = String(row.asset) as WalletAsset
        if (asset === 'AIR' || asset === 'USDT') {
            result[asset] = {
                available: String(row.available_amount || '0'),
                locked: String(row.locked_amount || '0'),
            }
        }
    }
    return result
}

async function updateBalance(userId: string, asset: WalletAsset, available: string, locked: string) {
    const { error } = await supabaseAdmin
        .from('wallet_balances')
        .update({ available_amount: available, locked_amount: locked })
        .eq('user_id', userId)
        .eq('asset', asset)
    if (error) throw error
}

async function insertLedger(input: {
    userId: string
    asset: WalletAsset
    direction: 'credit' | 'debit'
    amount: string
    availableAfter: string
    lockedAfter: string
    reason: string
    referenceType?: string
    referenceId?: string
    idempotencyKey?: string
    metadata?: Record<string, any>
}) {
    const { error } = await supabaseAdmin
        .from('wallet_ledger')
        .insert({
            user_id: input.userId,
            asset: input.asset,
            direction: input.direction,
            amount: input.amount,
            available_after: input.availableAfter,
            locked_after: input.lockedAfter,
            reason: input.reason,
            reference_type: input.referenceType || null,
            reference_id: input.referenceId || null,
            idempotency_key: input.idempotencyKey || null,
            metadata: input.metadata || {},
        })
    if (error && String(error.code || '') !== '23505') throw error
}

async function getAirDecimals(settings: WalletSettings): Promise<number> {
    return withRpcProvider(settings, async provider => {
        const token = new Contract(settings.airContractAddress, ERC20_ABI, provider)
        const decimals = await token.decimals()
        return Number(decimals || 18)
    })
}

async function actionMe(userId: string) {
    const wallet = await ensureStage1WalletForUser(userId)
    const settings = await loadWalletSettings()
    const balances = await getBalances(userId)
    return {
        success: true,
        wallet: publicStage1Wallet(wallet),
        wallet_address: wallet?.address || '',
        balances,
        settings: {
            chain_id: settings.chainId,
            air_contract_address: settings.airContractAddress,
            deposits_enabled: settings.depositsEnabled,
            swaps_enabled: settings.swapsEnabled,
            withdrawals_enabled: settings.withdrawalsEnabled,
            swap_fee_percent: settings.swapFeePercent,
            air_to_usdt_rate: settings.airToUsdtRate,
            usdt_to_air_rate: settings.usdtToAirRate,
            min_air_withdrawal: settings.minAirWithdrawal,
            min_usdt_withdrawal: settings.minUsdtWithdrawal,
            air_withdrawal_fee: settings.airWithdrawalFee,
            usdt_withdrawal_fee: settings.usdtWithdrawalFee,
        },
    }
}

async function actionSyncAirDeposits(userId: string) {
    const wallet = await ensureStage1WalletForUser(userId)
    if (!wallet?.address) return { success: false, error: '지갑이 생성되지 않았습니다.' }

    const settings = await loadWalletSettings()
    if (!settings.depositsEnabled) return { success: false, error: 'AIR 입금 감지가 비활성화되어 있습니다.' }
    if (!settings.rpcUrls.length) return { success: false, error: 'ERC20 RPC URL이 설정되지 않았습니다.' }
    if (!EVM_ADDRESS_RE.test(settings.airContractAddress)) return { success: false, error: 'AIR 컨트랙트 주소가 올바르지 않습니다.' }

    const decimals = await getAirDecimals(settings)
    const iface = new Interface(ERC20_ABI)
    const latestDepositRes = await supabaseAdmin
        .from('air_deposits')
        .select('block_number')
        .eq('user_id', userId)
        .order('block_number', { ascending: false })
        .limit(1)
    if (latestDepositRes.error) throw latestDepositRes.error

    const synced = await withRpcProvider(settings, async provider => {
        const latestBlock = await provider.getBlockNumber()
        const lastSyncedBlock = Number(latestDepositRes.data?.[0]?.block_number || 0)
        const fromBlock = lastSyncedBlock > 0 ? lastSyncedBlock + 1 : Math.max(0, latestBlock - 5000)
        const logs = await provider.getLogs({
            address: settings.airContractAddress,
            fromBlock,
            toBlock: latestBlock,
            topics: [TRANSFER_TOPIC, null, zeroPadValue(wallet.address, 32)],
        })
        return { latestBlock, fromBlock, logs }
    })

    let creditedCount = 0
    let creditedAmount = '0'
    for (const log of synced.logs) {
        const txHash = String(log.transactionHash || '')
        if (!EVM_TX_RE.test(txHash)) continue
        const logIndex = Number(log.index ?? 0)
        const parsed = iface.parseLog({ topics: [...log.topics], data: log.data })
        const from = String(parsed?.args?.from || '')
        const to = String(parsed?.args?.to || '')
        const value = parsed?.args?.value as bigint
        if (!value || to.toLowerCase() !== wallet.address.toLowerCase()) continue

        const amount = formatUnits(value, decimals)
        const insertRes = await supabaseAdmin
            .from('air_deposits')
            .insert({
                user_id: userId,
                chain_id: settings.chainId,
                air_contract_address: settings.airContractAddress,
                tx_hash: txHash,
                log_index: logIndex,
                block_number: Number(log.blockNumber || 0),
                from_address: from,
                to_address: to,
                amount,
                confirmations: Math.max(0, synced.latestBlock - Number(log.blockNumber || 0)),
                status: 'CONFIRMED',
                raw_event: {
                    transaction_hash: txHash,
                    block_hash: log.blockHash,
                    block_number: Number(log.blockNumber || 0),
                    log_index: logIndex,
                },
                confirmed_at: new Date().toISOString(),
            })
            .select('id')
            .single()

        if (insertRes.error) {
            if (String(insertRes.error.code || '') === '23505') continue
            throw insertRes.error
        }

        const balances = await getBalances(userId)
        const nextAvailable = addDecimal(balances.AIR.available, amount)
        await updateBalance(userId, 'AIR', nextAvailable, balances.AIR.locked)
        await insertLedger({
            userId,
            asset: 'AIR',
            direction: 'credit',
            amount,
            availableAfter: nextAvailable,
            lockedAfter: balances.AIR.locked,
            reason: 'air_deposit',
            referenceType: 'air_deposits',
            referenceId: insertRes.data.id,
            idempotencyKey: `air_deposit:${settings.chainId}:${txHash}:${logIndex}`,
            metadata: { from_address: from, to_address: to, block_number: Number(log.blockNumber || 0) },
        })
        creditedCount += 1
        creditedAmount = addDecimal(creditedAmount, amount)
    }

    return {
        success: true,
        credited_count: creditedCount,
        credited_amount: creditedAmount,
        scanned: {
            from_block: synced.fromBlock,
            to_block: synced.latestBlock,
            logs: synced.logs.length,
        },
        balances: await getBalances(userId),
    }
}

async function actionSwap(userId: string, params: any) {
    const fromAsset = String(params.from_asset || '').toUpperCase() as WalletAsset
    const toAsset = fromAsset === 'AIR' ? 'USDT' : fromAsset === 'USDT' ? 'AIR' : null
    const amount = String(params.amount || '').trim()
    if (!toAsset || (fromAsset !== 'AIR' && fromAsset !== 'USDT')) {
        return { success: false, error: '스왑 자산은 AIR 또는 USDT만 가능합니다.' }
    }
    if (!positiveDecimal(amount)) return { success: false, error: '스왑 수량은 0보다 커야 합니다.' }

    const settings = await loadWalletSettings()
    if (!settings.swapsEnabled) return { success: false, error: '스왑 기능이 비활성화되어 있습니다.' }
    const rate = fromAsset === 'AIR' ? settings.airToUsdtRate : settings.usdtToAirRate
    if (!positiveDecimal(rate)) return { success: false, error: '스왑 환율이 설정되지 않았습니다.' }

    const balances = await getBalances(userId)
    if (!gteDecimal(balances[fromAsset].available, amount)) {
        return { success: false, error: `${fromAsset} 잔액이 부족합니다.` }
    }

    const grossToAmount = mulDecimal(amount, rate)
    const feeRate = divDecimal(settings.swapFeePercent || '0', '100')
    const feeAmount = mulDecimal(grossToAmount, feeRate)
    const netToAmount = subDecimal(grossToAmount, feeAmount)
    if (!positiveDecimal(netToAmount)) return { success: false, error: '스왑 결과 수량이 0 이하입니다.' }

    const nextFromAvailable = subDecimal(balances[fromAsset].available, amount)
    const nextToAvailable = addDecimal(balances[toAsset].available, netToAmount)

    const swapRes = await supabaseAdmin
        .from('wallet_swaps')
        .insert({
            user_id: userId,
            from_asset: fromAsset,
            to_asset: toAsset,
            from_amount: amount,
            gross_to_amount: grossToAmount,
            fee_asset: toAsset,
            fee_amount: feeAmount,
            net_to_amount: netToAmount,
            rate,
            status: 'COMPLETED',
            request_snapshot: {
                swap_fee_percent: settings.swapFeePercent,
                requested_at: new Date().toISOString(),
            },
            completed_at: new Date().toISOString(),
        })
        .select('id')
        .single()
    if (swapRes.error) throw swapRes.error

    await updateBalance(userId, fromAsset, nextFromAvailable, balances[fromAsset].locked)
    await updateBalance(userId, toAsset, nextToAvailable, balances[toAsset].locked)
    await insertLedger({
        userId,
        asset: fromAsset,
        direction: 'debit',
        amount,
        availableAfter: nextFromAvailable,
        lockedAfter: balances[fromAsset].locked,
        reason: 'swap',
        referenceType: 'wallet_swaps',
        referenceId: swapRes.data.id,
        metadata: { to_asset: toAsset, rate },
    })
    await insertLedger({
        userId,
        asset: toAsset,
        direction: 'credit',
        amount: netToAmount,
        availableAfter: nextToAvailable,
        lockedAfter: balances[toAsset].locked,
        reason: 'swap',
        referenceType: 'wallet_swaps',
        referenceId: swapRes.data.id,
        metadata: { from_asset: fromAsset, gross_to_amount: grossToAmount, fee_amount: feeAmount, rate },
    })

    return {
        success: true,
        swap: {
            id: swapRes.data.id,
            from_asset: fromAsset,
            to_asset: toAsset,
            from_amount: amount,
            gross_to_amount: grossToAmount,
            fee_amount: feeAmount,
            net_to_amount: netToAmount,
            rate,
        },
        balances: await getBalances(userId),
    }
}

async function actionWithdraw(userId: string, params: any) {
    const asset = String(params.asset || 'USDT').toUpperCase() as WalletAsset
    const requestedAmount = String(params.amount || '').trim()
    const toAddress = String(params.to_address || params.dest_address || '').trim()
    const requestedNetwork = String(params.network || (asset === 'USDT' ? 'BEP20' : 'ERC20')).trim().toUpperCase()
    const network = requestedNetwork === 'BSC' || requestedNetwork === 'BSC_BEP20' || requestedNetwork === 'BEP-20'
        ? 'BEP20'
        : requestedNetwork

    if (asset !== 'AIR' && asset !== 'USDT') return { success: false, error: '출금 자산은 AIR 또는 USDT만 가능합니다.' }
    if (!positiveDecimal(requestedAmount)) return { success: false, error: '출금 신청 수량은 0보다 커야 합니다.' }
    if (!EVM_ADDRESS_RE.test(toAddress)) return { success: false, error: '지갑 주소는 0x로 시작하는 42자리 주소여야 합니다.' }
    if (asset === 'USDT' && network !== 'BEP20') return { success: false, error: 'USDT 출금 네트워크는 BEP20만 지원합니다.' }
    if (asset === 'AIR' && network !== 'ERC20') return { success: false, error: 'AIR 출금 네트워크는 ERC20만 지원합니다.' }

    const settings = await loadWalletSettings()
    if (!settings.withdrawalsEnabled) return { success: false, error: '출금 신청 기능이 비활성화되어 있습니다.' }
    const minAmount = asset === 'AIR' ? settings.minAirWithdrawal : settings.minUsdtWithdrawal
    const feeAmount = asset === 'AIR' ? settings.airWithdrawalFee : settings.usdtWithdrawalFee
    if (gtDecimal(minAmount, '0') && !gteDecimal(requestedAmount, minAmount)) {
        return { success: false, error: `최소 출금 신청 수량은 ${minAmount} ${asset} 입니다.` }
    }
    if (gtDecimal(feeAmount, requestedAmount)) {
        return { success: false, error: '출금 수수료가 신청 수량보다 큽니다.' }
    }
    const netAmount = subDecimal(requestedAmount, feeAmount)
    if (!positiveDecimal(netAmount)) return { success: false, error: '수수료 차감 후 전송 수량이 0 이하입니다.' }

    const balances = await getBalances(userId)
    if (!gteDecimal(balances[asset].available, requestedAmount)) {
        return { success: false, error: `${asset} 잔액이 부족합니다.` }
    }

    const nextAvailable = subDecimal(balances[asset].available, requestedAmount)
    const nextLocked = addDecimal(balances[asset].locked, requestedAmount)
    const withdrawalRes = await supabaseAdmin
        .from('wallet_withdrawal_requests')
        .insert({
            user_id: userId,
            asset,
            network,
            to_address: toAddress,
            requested_amount: requestedAmount,
            fee_amount: feeAmount,
            net_amount: netAmount,
            status: 'REQUESTED',
            request_snapshot: {
                requested_at: new Date().toISOString(),
                fee_amount: feeAmount,
                min_amount: minAmount,
                stage1_manual_usdt: asset === 'USDT',
            },
        })
        .select('id')
        .single()
    if (withdrawalRes.error) throw withdrawalRes.error

    await updateBalance(userId, asset, nextAvailable, nextLocked)
    await insertLedger({
        userId,
        asset,
        direction: 'debit',
        amount: requestedAmount,
        availableAfter: nextAvailable,
        lockedAfter: nextLocked,
        reason: 'withdrawal_request',
        referenceType: 'wallet_withdrawal_requests',
        referenceId: withdrawalRes.data.id,
        metadata: { network, to_address: toAddress, fee_amount: feeAmount, net_amount: netAmount },
    })

    return {
        success: true,
        withdrawal: {
            id: withdrawalRes.data.id,
            asset,
            network,
            to_address: toAddress,
            requested_amount: requestedAmount,
            fee_amount: feeAmount,
            net_amount: netAmount,
            status: 'REQUESTED',
        },
        balances: await getBalances(userId),
    }
}

async function actionHistory(userId: string) {
    const [deposits, swaps, withdrawals, ledger] = await Promise.all([
        supabaseAdmin
            .from('air_deposits')
            .select('id,tx_hash,from_address,to_address,amount,status,block_number,created_at,confirmed_at')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(100),
        supabaseAdmin
            .from('wallet_swaps')
            .select('id,from_asset,to_asset,from_amount,gross_to_amount,fee_amount,net_to_amount,rate,status,created_at,completed_at')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(100),
        supabaseAdmin
            .from('wallet_withdrawal_requests')
            .select('id,asset,network,to_address,requested_amount,fee_amount,net_amount,status,tx_hash,admin_memo,failure_reason,created_at,approved_at,sent_at,completed_at,rejected_at,failed_at')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(100),
        supabaseAdmin
            .from('wallet_ledger')
            .select('id,asset,direction,amount,available_after,locked_after,reason,reference_type,reference_id,metadata,created_at')
            .eq('user_id', userId)
            .order('created_at', { ascending: false })
            .limit(200),
    ])

    for (const res of [deposits, swaps, withdrawals, ledger]) {
        if (res.error) throw res.error
    }

    return {
        success: true,
        deposits: deposits.data || [],
        swaps: swaps.data || [],
        withdrawals: withdrawals.data || [],
        ledger: ledger.data || [],
    }
}

export async function POST(req: Request) {
    try {
        const body = await req.json()
        const { email, session_token, action } = body || {}
        if (!email || !session_token || !action) {
            return NextResponse.json({ success: false, error: 'Missing email, session_token or action' }, { status: 400 })
        }

        const normalizedEmail = String(email)
        if (!(await verifyApprovedDesktopSession(normalizedEmail, String(session_token)))) {
            return NextResponse.json({ success: false, error: '세션이 만료되었거나 유효하지 않습니다. 다시 로그인해주세요.' }, { status: 401 })
        }

        const userId = await resolveUserId(normalizedEmail)
        if (!userId) return NextResponse.json({ success: false, error: '등록되지 않은 사용자입니다.' }, { status: 404 })

        switch (String(action)) {
            case 'me':
                return NextResponse.json(await actionMe(userId))
            case 'sync_air_deposits':
                return NextResponse.json(await actionSyncAirDeposits(userId))
            case 'swap':
                return NextResponse.json(await actionSwap(userId, body))
            case 'withdraw':
                return NextResponse.json(await actionWithdraw(userId, body))
            case 'history':
                return NextResponse.json(await actionHistory(userId))
            default:
                return NextResponse.json({ success: false, error: `Unknown action: ${action}` }, { status: 400 })
        }
    } catch (error: any) {
        console.error('[DesktopWallet] error:', error?.message || error)
        return NextResponse.json({ success: false, error: error?.message || '지갑 서버 오류' }, { status: 500 })
    }
}
