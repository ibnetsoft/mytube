import { Wallet } from 'ethers'
import { supabaseAdmin } from './supabaseAdmin'

const DEFAULT_CHAIN_ID = 1

export type Stage1Wallet = {
    user_id: string
    address: string
    chain_id: number
    created: boolean
}

function normalizeChainId(value: unknown): number {
    const parsed = Number.parseInt(String(value || ''), 10)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_CHAIN_ID
}

async function getWalletChainId(): Promise<number> {
    const { data, error } = await supabaseAdmin
        .from('global_settings')
        .select('value')
        .eq('key', 'wallet_chain_id')
        .maybeSingle()

    if (error) {
        console.warn('[WalletStage1] wallet_chain_id setting fetch failed:', error.message)
        return DEFAULT_CHAIN_ID
    }
    return normalizeChainId(data?.value)
}

async function fetchExistingWallet(userId: string): Promise<Stage1Wallet | null> {
    const { data, error } = await supabaseAdmin
        .from('wallet_accounts')
        .select('user_id,address,chain_id')
        .eq('user_id', userId)
        .maybeSingle()

    if (error) throw error
    if (!data?.address) return null
    return {
        user_id: String(data.user_id),
        address: String(data.address),
        chain_id: normalizeChainId(data.chain_id),
        created: false,
    }
}

async function ensureZeroBalanceRows(userId: string) {
    const { error } = await supabaseAdmin
        .from('wallet_balances')
        .upsert([
            { user_id: userId, asset: 'AIR', available_amount: '0', locked_amount: '0' },
            { user_id: userId, asset: 'USDT', available_amount: '0', locked_amount: '0' },
        ], { onConflict: 'user_id,asset' })

    if (error) throw error
}

async function syncLegacyProfileWalletAddress(userId: string, address: string) {
    const { error } = await supabaseAdmin
        .from('profiles')
        .update({ wallet_address: address })
        .eq('id', userId)

    // Older/local schemas may not have the compatibility column. The canonical
    // stage-1 wallet address remains wallet_accounts.address, so do not block
    // login/signup on this legacy mirror.
    if (error && !['42703', 'PGRST204'].includes(String(error.code || ''))) {
        console.warn('[WalletStage1] legacy profile wallet sync failed:', error.message)
    }
}

export async function ensureStage1WalletForUser(userId: string): Promise<Stage1Wallet | null> {
    if (!userId) return null

    try {
        const existing = await fetchExistingWallet(userId)
        if (existing) {
            await ensureZeroBalanceRows(userId)
            await syncLegacyProfileWalletAddress(userId, existing.address)
            return existing
        }

        const chainId = await getWalletChainId()
        const generated = Wallet.createRandom()
        const payload = {
            user_id: userId,
            chain_id: chainId,
            address: generated.address,
            private_key: generated.privateKey,
            key_storage_mode: 'plain_db',
            status: 'ACTIVE',
            metadata: {
                source: 'auth-web',
                created_by: 'stage1_auto_wallet',
            },
        }

        const { data, error } = await supabaseAdmin
            .from('wallet_accounts')
            .insert(payload)
            .select('user_id,address,chain_id')
            .single()

        if (error) {
            // Concurrent login/signup can race on the unique user_id. If the
            // other request created it first, return that wallet.
            if (String(error.code || '') === '23505') {
                const raced = await fetchExistingWallet(userId)
                if (raced) {
                    await ensureZeroBalanceRows(userId)
                    await syncLegacyProfileWalletAddress(userId, raced.address)
                    return raced
                }
            }
            throw error
        }

        await ensureZeroBalanceRows(userId)
        await syncLegacyProfileWalletAddress(userId, String(data.address))

        return {
            user_id: String(data.user_id),
            address: String(data.address),
            chain_id: normalizeChainId(data.chain_id),
            created: true,
        }
    } catch (error: any) {
        // The migration may not be applied yet in early rollout. Keep auth
        // usable and log the exact server-side failure for deployment checks.
        console.warn('[WalletStage1] ensure wallet skipped:', error?.message || error)
        return null
    }
}

export function publicStage1Wallet(wallet: Stage1Wallet | null) {
    if (!wallet) return null
    return {
        address: wallet.address,
        chain_id: wallet.chain_id,
        assets: {
            AIR: { available: '0', locked: '0' },
            USDT: { available: '0', locked: '0' },
        },
        created: wallet.created,
    }
}
