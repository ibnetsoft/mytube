'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'

// AIR-0223: every admin API route under /api/admin/referrals/** uses the
// Bearer-token auth pattern from _auth.ts (getRequester reads the
// Authorization header), not the cookie-session pattern some older pages in
// this app use. This hook follows the pattern that's actually proven to work
// (components/DashboardContent.tsx: supabase.auth.getSession() -> access_token).
export function useAuthToken() {
    const [token, setToken] = useState<string>('')
    const [ready, setReady] = useState(false)

    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            setToken(session?.access_token || '')
            setReady(true)
        })
    }, [])

    return { token, ready }
}

export async function authedFetch(token: string, url: string, init?: RequestInit): Promise<Response> {
    const headers = new Headers(init?.headers)
    if (token) headers.set('Authorization', `Bearer ${token}`)
    if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    return fetch(url, { ...init, headers })
}

export function formatUsd(value: number | null | undefined): string {
    const n = Number(value) || 0
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatDate(value: string | null | undefined): string {
    if (!value) return '-'
    try {
        return new Date(value).toLocaleString()
    } catch {
        return value
    }
}

export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
    if (rows.length === 0) return
    const headers = Object.keys(rows[0])
    const escape = (v: unknown) => {
        const s = v === null || v === undefined ? '' : String(v)
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    }
    const csv = [headers.join(','), ...rows.map(r => headers.map(h => escape(r[h])).join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}
