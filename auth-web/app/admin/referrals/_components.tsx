'use client'

import Link from 'next/link'
import { formatUsd } from './_hooks'

export interface OrgMemberCardData {
    id: string
    email: string
    full_name: string | null
    country: string | null
    is_active: boolean
    direct_referrals: number
    commission_total: number
    commission_level1_total: number
    commission_level2_total: number
}

// AIR-0225: replaces the plain "name — $total" list row in the org Tree
// View with a card that surfaces country, activity, and the L1/L2
// commission split without an extra click to the member detail page.
export function OrgMemberCard({ row, isRoot = false }: { row: OrgMemberCardData; isRoot?: boolean }) {
    const initial = (row.full_name || row.email || '?').trim().charAt(0).toUpperCase() || '?'
    const l1 = row.commission_level1_total || 0
    const l2 = row.commission_level2_total || 0
    const total = row.commission_total || 0
    const l1Pct = total > 0 ? Math.min(100, Math.round((l1 / total) * 100)) : 0
    const l2Pct = total > 0 ? Math.max(0, 100 - l1Pct) : 0

    return (
        <div
            className={`w-[220px] shrink-0 rounded-2xl border p-3.5 shadow-lg shadow-black/20 ${
                isRoot ? 'border-indigo-500 bg-gray-900 ring-1 ring-indigo-500/30' : 'border-gray-800 bg-gray-900/80'
            }`}
        >
            <div className="mb-2.5 flex items-center gap-2.5">
                <div
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                        isRoot ? 'bg-indigo-600 text-white' : 'bg-indigo-500/15 text-indigo-400'
                    }`}
                >
                    {initial}
                </div>
                <div className="min-w-0">
                    <Link
                        href={`/admin/referrals/members/${row.id}`}
                        className="block truncate text-[13px] font-semibold text-gray-100 hover:text-indigo-400 hover:underline"
                    >
                        {row.full_name || row.email}
                    </Link>
                    <div className="truncate text-[11px] text-gray-500">{row.email}</div>
                </div>
            </div>

            <div className="mb-2.5 flex items-center gap-1.5">
                {row.country && (
                    <span className="rounded-full border border-gray-700 bg-gray-800 px-2 py-0.5 text-[10px] font-bold text-gray-400">
                        {row.country}
                    </span>
                )}
                <span
                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        row.is_active ? 'bg-emerald-500/10 text-emerald-400' : 'bg-gray-700/30 text-gray-500'
                    }`}
                >
                    <span className={`h-1.5 w-1.5 rounded-full ${row.is_active ? 'bg-emerald-400' : 'bg-gray-500'}`} />
                    {row.is_active ? '활성' : '비활성'}
                </span>
            </div>

            <div className="mb-1.5 flex items-baseline justify-between">
                <span className="font-mono text-lg font-bold tabular-nums text-white">${formatUsd(total)}</span>
                <span className="text-[10px] uppercase tracking-wide text-gray-600">합계</span>
            </div>

            <div className="mb-2 flex h-1.5 overflow-hidden rounded-full bg-gray-800">
                {l1Pct > 0 && <div className="h-full bg-indigo-500" style={{ width: `${l1Pct}%` }} />}
                {l2Pct > 0 && <div className="h-full bg-gray-500/60" style={{ width: `${l2Pct}%` }} />}
            </div>

            <div className="flex justify-between text-[10.5px] text-gray-500">
                <span>
                    L1 ${formatUsd(l1)} · L2 ${formatUsd(l2)}
                </span>
                <span className="font-mono font-semibold text-gray-300">직속 {row.direct_referrals}명</span>
            </div>
        </div>
    )
}

export function LoadingBlock({ label = '불러오는 중...' }: { label?: string }) {
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

export function EmptyBlock({ label = '데이터가 없습니다.' }: { label?: string }) {
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
                {page} / {totalPages} 페이지 (총 {total}건)
            </div>
            <div className="flex gap-2">
                <button
                    className="px-3 py-1 rounded border border-gray-700 disabled:opacity-40"
                    disabled={page <= 1}
                    onClick={() => onPage(page - 1)}
                >
                    이전
                </button>
                <button
                    className="px-3 py-1 rounded border border-gray-700 disabled:opacity-40"
                    disabled={page >= totalPages}
                    onClick={() => onPage(page + 1)}
                >
                    다음
                </button>
            </div>
        </div>
    )
}

export const STATUS_LABELS_KO: Record<string, string> = {
    REQUESTED: '요청됨',
    APPROVED: '승인됨',
    SENDING: '전송 중',
    COMPLETED: '완료',
    PAID: '지급완료',
    REJECTED: '반려됨',
    PENDING: '대기중',
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
    return <span className={`px-2 py-0.5 rounded text-xs font-semibold border ${cls}`}>{STATUS_LABELS_KO[s] || s}</span>
}
