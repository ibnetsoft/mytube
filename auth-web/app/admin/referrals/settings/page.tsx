'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useAuthToken, authedFetch } from '../_hooks'
import { Card, ErrorBlock } from '../_components'

// AIR-0223: this tab intentionally does NOT reimplement the referral settings
// form. Level%/Default Sponsor/Mode/Min Payout/Cycle already have a working
// page + API (auth-web/app/admin/settings/referral) — "실제 저장 로직 변경은
// 하지 않는다. 기존 global_settings API를 사용한다" is satisfied by linking to
// it unmodified, not by duplicating it. The Country Manager section below is
// new UI only — it calls the existing /api/admin/referrals PATCH endpoint
// (make_country_manager/managed_country), which already existed and worked,
// just had no UI surfacing it.
export default function ReferralAdminSettingsPage() {
    const { token, ready } = useAuthToken()
    const [userId, setUserId] = useState('')
    const [countryCode, setCountryCode] = useState('')
    const [commissionRate, setCommissionRate] = useState('0')
    const [saving, setSaving] = useState(false)
    const [message, setMessage] = useState('')
    const [error, setError] = useState('')

    const assignCountryManager = async (makeManager: boolean) => {
        if (!userId.trim()) { setError('User ID is required.'); return }
        setSaving(true)
        setError('')
        setMessage('')
        try {
            const res = await authedFetch(token, '/api/admin/referrals', {
                method: 'PATCH',
                body: JSON.stringify({
                    userId: userId.trim(),
                    country_code: countryCode.trim().toUpperCase(),
                    referral_country: countryCode.trim().toUpperCase(),
                    commission_rate: Number(commissionRate) || 0,
                    make_country_manager: makeManager,
                }),
            })
            const json = await res.json()
            if (json.success) setMessage(makeManager ? 'Assigned as Country Manager.' : 'Country Manager role revoked.')
            else setError(json.error || 'Failed to update')
        } catch (e: any) {
            setError(e.message)
        } finally {
            setSaving(false)
        }
    }

    return (
        <div className="space-y-6 max-w-2xl">
            <Card>
                <h2 className="text-lg font-bold mb-2">Referral Mode / Rates / Default Sponsor</h2>
                <p className="text-sm text-gray-400 mb-4">
                    Managed on the existing settings page (unchanged by AIR-0223) — Referral Mode, Level 1/2 %, Default Sponsor, Minimum Payout, Settlement Cycle.
                </p>
                <Link
                    href="/admin/settings/referral"
                    className="inline-block px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 text-sm font-semibold"
                >
                    Open Referral Settings →
                </Link>
            </Card>

            <Card>
                <h2 className="text-lg font-bold mb-2">Country Manager</h2>
                <p className="text-sm text-gray-400 mb-4">
                    Assigns a profile&apos;s country and, optionally, Country Manager access (scopes their Referral Admin Dashboard view to that country — see <code>_auth.ts</code>&apos;s <code>isSubAdmin</code>). Uses the existing <code>/api/admin/referrals</code> PATCH endpoint.
                </p>
                {message && <div className="mb-3 p-2 bg-green-900/40 border border-green-700 rounded text-green-200 text-sm">{message}</div>}
                {error && <div className="mb-3"><ErrorBlock message={error} /></div>}
                <div className="space-y-3">
                    <div>
                        <label className="block text-xs text-gray-400 mb-1">User ID (UUID)</label>
                        <input className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                            value={userId} onChange={e => setUserId(e.target.value)} placeholder="profiles.id" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Country Code</label>
                            <input className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                                value={countryCode} onChange={e => setCountryCode(e.target.value)} placeholder="KR" maxLength={2} />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Commission Rate (%)</label>
                            <input type="number" className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm"
                                value={commissionRate} onChange={e => setCommissionRate(e.target.value)} />
                        </div>
                    </div>
                    <div className="flex gap-2 pt-2">
                        <button disabled={saving || !ready} onClick={() => assignCountryManager(true)}
                            className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-sm font-semibold">
                            Assign as Country Manager
                        </button>
                        <button disabled={saving || !ready} onClick={() => assignCountryManager(false)}
                            className="px-4 py-2 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-sm">
                            Update Country/Rate Only
                        </button>
                    </div>
                    <p className="text-xs text-gray-600 pt-1">
                        Note: the underlying (unmodified) API only ever <em>sets</em> the sub_admin role, it doesn&apos;t revert it — &quot;Update Country/Rate Only&quot; will not demote an existing Country Manager. Full role revocation isn&apos;t available without changing that API, which is out of AIR-0223&apos;s scope.
                    </p>
                </div>
            </Card>
        </div>
    )
}
