export type LongformPayoutTier = {
    max_minutes: number
    payout_usdt: number
}

export type LongformScenePayoutTier = {
    max_scenes: number
    payout_usdt: number
}

export const DEFAULT_LONGFORM_MAX_DURATION_MINUTES = 150
export const DEFAULT_LONGFORM_MAX_PAYOUT_USDT = 10

export const DEFAULT_LONGFORM_PAYOUT_TIERS: LongformPayoutTier[] = [
    { max_minutes: 15, payout_usdt: 4 },
    { max_minutes: 30, payout_usdt: 5 },
    { max_minutes: 60, payout_usdt: 6 },
    { max_minutes: 90, payout_usdt: 7 },
    { max_minutes: 120, payout_usdt: 8 },
    { max_minutes: 150, payout_usdt: 9 },
]

export const DEFAULT_LONGFORM_SCENE_PAYOUT_TIERS: LongformScenePayoutTier[] = [
    { max_scenes: 40, payout_usdt: 3 },
    { max_scenes: 70, payout_usdt: 4 },
    { max_scenes: 100, payout_usdt: 5 },
    { max_scenes: 150, payout_usdt: 7 },
    { max_scenes: 220, payout_usdt: 10 },
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
    const tiers = normalizeLongformPayoutTiers(tiersValue)
    const duration = Math.max(1, Math.round(Number(minutes) || 0))
    const matched = tiers.find((tier) => duration <= tier.max_minutes) || tiers[tiers.length - 1]
    return Math.round(matched.payout_usdt * 10) / 10
}

export function calculateLongformPayoutByScenes(sceneCount: number): number {
    const scenes = Math.max(1, Math.round(Number(sceneCount) || 0))
    const matched = DEFAULT_LONGFORM_SCENE_PAYOUT_TIERS.find((tier) => scenes <= tier.max_scenes)
        || DEFAULT_LONGFORM_SCENE_PAYOUT_TIERS[DEFAULT_LONGFORM_SCENE_PAYOUT_TIERS.length - 1]
    return Math.min(DEFAULT_LONGFORM_MAX_PAYOUT_USDT, Math.round(matched.payout_usdt * 10) / 10)
}

export function capLongformPayout(value: number): number {
    const amount = Math.max(0, Number(value) || 0)
    return Math.min(DEFAULT_LONGFORM_MAX_PAYOUT_USDT, Math.round(amount * 10) / 10)
}
