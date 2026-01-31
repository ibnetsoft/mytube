
'use client'

import dynamic from 'next/dynamic'

const DashboardContent = dynamic(
    () => import('@/components/DashboardContent'),
    {
        ssr: false,
        loading: () => <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">Loading Dashboard...</div>
    }
)

export default function DashboardPage() {
    return <DashboardContent />
}
