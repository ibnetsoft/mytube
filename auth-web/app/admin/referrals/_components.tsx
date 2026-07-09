'use client'

export function LoadingBlock({ label = 'Loading...' }: { label?: string }) {
    return (
        <div className="flex items-center justify-center py-16 text-gray-400">
            <svg className="animate-spin h-5 w-5 mr-3" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            {label}
        </div>
    )
}

export function EmptyBlock({ label = 'No data found.' }: { label?: string }) {
    return <div className="text-center py-16 text-gray-500 text-sm">{label}</div>
}

export function ErrorBlock({ message }: { message: string }) {
    return (
        <div className="p-3 bg-red-900/40 border border-red-700 rounded text-red-200 text-sm">{message}</div>
    )
}

export function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
    return <div className={`bg-gray-900 border border-gray-800 rounded-xl p-5 ${className}`}>{children}</div>
}

export function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
    return (
        <Card>
            <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
            <div className="text-2xl font-bold mt-1 break-words">{value}</div>
            {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
        </Card>
    )
}

export function Pagination({
    page, limit, total, onPage,
}: { page: number; limit: number; total: number; onPage: (p: number) => void }) {
    const totalPages = Math.max(1, Math.ceil(total / limit))
    if (totalPages <= 1) return null
    return (
        <div className="flex items-center justify-between mt-4 text-sm text-gray-400">
            <div>
                Page {page} / {totalPages} ({total} total)
            </div>
            <div className="flex gap-2">
                <button
                    className="px-3 py-1 rounded border border-gray-700 disabled:opacity-40"
                    disabled={page <= 1}
                    onClick={() => onPage(page - 1)}
                >
                    Prev
                </button>
                <button
                    className="px-3 py-1 rounded border border-gray-700 disabled:opacity-40"
                    disabled={page >= totalPages}
                    onClick={() => onPage(page + 1)}
                >
                    Next
                </button>
            </div>
        </div>
    )
}

export function StatusBadge({ status }: { status: string }) {
    const s = String(status || '').toUpperCase()
    const colorMap: Record<string, string> = {
        REQUESTED: 'bg-yellow-900 text-yellow-300 border-yellow-700',
        APPROVED: 'bg-blue-900 text-blue-300 border-blue-700',
        SENDING: 'bg-purple-900 text-purple-300 border-purple-700',
        COMPLETED: 'bg-green-900 text-green-300 border-green-700',
        PAID: 'bg-green-900 text-green-300 border-green-700',
        REJECTED: 'bg-red-900 text-red-300 border-red-700',
        PENDING: 'bg-yellow-900 text-yellow-300 border-yellow-700',
    }
    const cls = colorMap[s] || 'bg-gray-800 text-gray-300 border-gray-700'
    return <span className={`px-2 py-0.5 rounded text-xs font-semibold border ${cls}`}>{s}</span>
}
