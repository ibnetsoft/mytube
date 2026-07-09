'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const TABS = [
    { href: '/admin/referrals', label: 'Dashboard' },
    { href: '/admin/referrals/organization', label: 'Organization' },
    { href: '/admin/referrals/commissions', label: 'Commission' },
    { href: '/admin/referrals/withdrawals', label: 'Withdrawals' },
    { href: '/admin/referrals/audit', label: 'Audit' },
    { href: '/admin/referrals/settings', label: 'Settings' },
]

export default function ReferralAdminLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname()

    return (
        <div className="min-h-screen bg-gray-950 text-white">
            <div className="border-b border-gray-800 bg-gray-900 sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 sm:px-6">
                    <h1 className="text-xl font-bold pt-4">Referral Admin Dashboard</h1>
                    <nav className="flex flex-wrap gap-1 mt-3 -mb-px overflow-x-auto">
                        {TABS.map(tab => {
                            const active = tab.href === '/admin/referrals'
                                ? pathname === tab.href
                                : pathname?.startsWith(tab.href)
                            return (
                                <Link
                                    key={tab.href}
                                    href={tab.href}
                                    className={`px-3 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                                        active
                                            ? 'border-indigo-500 text-indigo-400'
                                            : 'border-transparent text-gray-400 hover:text-gray-200'
                                    }`}
                                >
                                    {tab.label}
                                </Link>
                            )
                        })}
                    </nav>
                </div>
            </div>
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">{children}</div>
        </div>
    )
}
