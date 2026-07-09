import { createClient } from '@supabase/supabase-js'
import type { AdminCheck } from '../_auth'

// AIR-0223: shared helpers for the Referral Admin Dashboard's API routes.
// Not a general abstraction — scoped to this feature's routes only, to avoid
// repeating the same pagination/country-scoping logic across all 7 of them.

export const getAdmin = () => createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    { auth: { persistSession: false } }
)

export function parsePagination(searchParams: URLSearchParams, defaultLimit = 20, maxLimit = 100) {
    const page = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1)
    const limit = Math.min(maxLimit, Math.max(1, Number.parseInt(searchParams.get('limit') || String(defaultLimit), 10) || defaultLimit))
    const offset = (page - 1) * limit
    return { page, limit, offset }
}

// Superadmins see everything. Country managers (app_metadata.role === 'sub_admin',
// per the existing _auth.ts isSubAdmin concept and the existing
// /api/admin/referrals PATCH's make_country_manager/managed_country fields)
// only see their own managed_country. Returns '' for "no scoping" (superadmin).
export function scopedCountry(requester: AdminCheck): string {
    if (requester.isSuperAdmin) return ''
    const managed = (requester.user.app_metadata as Record<string, unknown> | undefined)?.managed_country
    return managed ? String(managed).toUpperCase() : ''
}

export function matchesCountryScope(
    profile: { referral_country?: string | null; country_code?: string | null },
    scope: string
): boolean {
    if (!scope) return true
    const country = String(profile.referral_country || profile.country_code || '').toUpperCase()
    return country === scope
}

export function displayName(profile: { full_name?: string | null; email?: string | null } | null | undefined): string {
    if (!profile) return 'Unknown'
    return profile.full_name || (profile.email ? profile.email.split('@')[0] : '') || 'Unknown'
}
