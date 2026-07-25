// Thin standalone-route wrapper - the actual UI lives in
// components/ErrorLogsPanel.tsx so it can also be embedded inline in the
// main dashboard (see DashboardContent.tsx).
import ErrorLogsPanel from '../../../components/ErrorLogsPanel'

export default function AdminLogsPage() {
    return (
        <div className="min-h-screen bg-gray-950 text-white">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
                <ErrorLogsPanel />
            </div>
        </div>
    )
}
