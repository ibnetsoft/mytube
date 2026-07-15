'use client'

import { useState } from 'react'
import ReferralDashboardPage from '../app/admin/referrals/page'
import OrganizationPage from '../app/admin/referrals/organization/page'
import CommissionsPage from '../app/admin/referrals/commissions/page'
import WithdrawalsPage from '../app/admin/referrals/withdrawals/page'
import AuditPage from '../app/admin/referrals/audit/page'
import ReferralAdminSettingsPage from '../app/admin/referrals/settings/page'

// [AIR-0228] Embeds the Referral Admin section inline in the main dashboard
// instead of navigating to a separate /admin/referrals page - keeps the
// outer AIR STUDIO header + tab bar visible at all times. Each sub-page
// component is unchanged internally (still fetches its own data via
// useAuthToken/authedFetch) - only the outer routing/layout chrome is
// replaced with local tab state here.
const SUB_TABS = [
    { id: 'dashboard', label: '대시보드' },
    { id: 'organization', label: '조직도' },
    { id: 'commissions', label: '커미션' },
    { id: 'withdrawals', label: '출금' },
    { id: 'audit', label: '감사 로그' },
    { id: 'settings', label: '설정' },
] as const

type SubTabId = typeof SUB_TABS[number]['id']

export default function ReferralAdminPanel() {
    const [subTab, setSubTab] = useState<SubTabId>('dashboard')

    return (
        <div className="space-y-6 animate-in fade-in duration-300">
            <div>
                <h2 className="text-lg font-black mb-3">추천인 관리</h2>
                <div className="flex flex-wrap gap-1.5">
                    {SUB_TABS.map(tab => (
                        <button
                            key={tab.id}
                            type="button"
                            onClick={() => setSubTab(tab.id)}
                            className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors ${
                                subTab === tab.id
                                    ? 'bg-indigo-600 text-white'
                                    : 'bg-gray-900 text-gray-400 hover:text-gray-200 border border-gray-800'
                            }`}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>
            </div>

            <div className="bg-gray-950/40 border border-white/5 rounded-2xl p-5 text-white">
                {subTab === 'dashboard' && <ReferralDashboardPage />}
                {subTab === 'organization' && <OrganizationPage />}
                {subTab === 'commissions' && <CommissionsPage />}
                {subTab === 'withdrawals' && <WithdrawalsPage />}
                {subTab === 'audit' && <AuditPage />}
                {subTab === 'settings' && <ReferralAdminSettingsPage />}
            </div>
        </div>
    )
}
