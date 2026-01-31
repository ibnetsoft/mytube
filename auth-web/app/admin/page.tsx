
'use client'

import dynamic from 'next/dynamic'

// ssr: false 설정을 통해 서버에서는 아예 그리지 않고 브라우저에서만 그리게 합니다.
// 이렇게 하면 Hydration Error (서버/클라이언트 불일치)가 100% 발생하지 않습니다.
const AdminDashboardContent = dynamic(
    () => import('@/components/AdminDashboardContent'),
    {
        ssr: false,
        loading: () => <div className="text-white p-10 text-center bg-gray-900 min-h-screen">Loading Admin Panel...</div>
    }
)

export default function AdminPage() {
    return <AdminDashboardContent />
}
