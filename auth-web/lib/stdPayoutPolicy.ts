export type LongformPayoutTier = {
    max_minutes: number
    payout_usdt: number
}

export type LongformScenePayoutTier = {
    max_scenes: number
    payout_usdt: number
}

export const DEFAULT_LONGFORM_MAX_DURATION_MINUTES = 150
export const FIXED_LONGFORM_PAYOUT_USDT = 2.5
export const DEFAULT_LONGFORM_MAX_PAYOUT_USDT = FIXED_LONGFORM_PAYOUT_USDT

export const DEFAULT_LONGFORM_PAYOUT_TIERS: LongformPayoutTier[] = [
    { max_minutes: DEFAULT_LONGFORM_MAX_DURATION_MINUTES, payout_usdt: FIXED_LONGFORM_PAYOUT_USDT },
]

export const DEFAULT_LONGFORM_SCENE_PAYOUT_TIERS: LongformScenePayoutTier[] = [
    { max_scenes: Number.MAX_SAFE_INTEGER, payout_usdt: FIXED_LONGFORM_PAYOUT_USDT },
]

export const DEFAULT_LONGFORM_PAYOUT_TIERS_JSON = JSON.stringify(DEFAULT_LONGFORM_PAYOUT_TIERS, null, 2)

function toFloat(value: any, fallback: number): number {
    const parsed = Number.parseFloat(String(value ?? ''))
    return Number.isFinite(parsed) ? parsed : fallback
}

export function normalizeLongformPayoutTiers(value: any): LongformPayoutTier[] {
    let parsed = value
    if (typeof value === 'string') {
        const trimmed = value.trim()
        if (!trimmed) return DEFAULT_LONGFORM_PAYOUT_TIERS
        try {
            parsed = JSON.parse(trimmed)
        } catch {
            return DEFAULT_LONGFORM_PAYOUT_TIERS
        }
    }

    if (!Array.isArray(parsed)) return DEFAULT_LONGFORM_PAYOUT_TIERS

    const tiers = parsed
        .map((tier: any) => {
            const maxMinutes = Math.round(toFloat(tier?.max_minutes ?? tier?.minutes ?? tier?.max, 0))
            const payoutUsdt = toFloat(tier?.payout_usdt ?? tier?.payout ?? tier?.amount, 0)
            return maxMinutes > 0 && payoutUsdt > 0
                ? { max_minutes: maxMinutes, payout_usdt: Math.round(payoutUsdt * 10) / 10 }
                : null
        })
        .filter(Boolean) as LongformPayoutTier[]

    if (!tiers.length) return DEFAULT_LONGFORM_PAYOUT_TIERS
    return tiers.sort((a, b) => a.max_minutes - b.max_minutes)
}

export function calculateLongformPayoutByTiers(minutes: number, tiersValue: any): number {
    return FIXED_LONGFORM_PAYOUT_USDT
}

export function calculateLongformPayoutByScenes(sceneCount: number): number {
    return FIXED_LONGFORM_PAYOUT_USDT
}

export function capLongformPayout(value: number): number {
    return FIXED_LONGFORM_PAYOUT_USDT
}
