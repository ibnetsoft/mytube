'use client'

import { useEffect, useState } from 'react'
import { useAuthToken, authedFetch, formatDate } from '../referrals/_hooks'

// [AIR-0227D Stage 16] Minimal admin visibility for staging QA - worker
// list, online/offline, current lease job, token state. Not a full ops
// dashboard by design (task scope explicitly excludes a large UI redesign).
// Follows the admin/referrals Bearer-token fetch pattern (_hooks.ts), not
// the older cookie-session pattern some other admin pages still use.

interface WorkerRow {
    worker_id: string
    worker_group: string
    allowed_job_types: string[]
    online: boolean
    last_heartbeat_at: string | null
    token_revoked: boolean
    token_prefix: string | null
    current_job: {
        job_id: string
        worker_status: string | null
        status: string
        progress: number
        retry_count: number
        error_code: string | null
        lease_expires_at: string | null
    } | null
}

export default function WorkersPage() {
    const { token, ready } = useAuthToken()
    const [workers, setWorkers] = useState<WorkerRow[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [issuing, setIssuing] = useState(false)
    const [newWorkerId, setNewWorkerId] = useState('')
    const [issuedToken, setIssuedToken] = useState<{ worker_id: string; token: string } | null>(null)

    const fetchWorkers = async () => {
        if (!token) return
        setLoading(true)
        setError('')
        try {
            const res = await authedFetch(token, '/api/admin/workers')
            const data = await res.json()
            if (res.ok) {
                setWorkers(data.workers || [])
            } else {
                setError(data.error || 'Failed to fetch workers')
            }
        } catch (err: any) {
            setError(err.message || 'Unknown error')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (ready) fetchWorkers()
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ready])

    const issueToken = async () => {
        if (!newWorkerId.trim()) return
        setIssuing(true)
        setError('')
        setIssuedToken(null)
        try {
            const res = await authedFetch(token, '/api/admin/worker-tokens', {
                method: 'POST',
                body: JSON.stringify({ worker_id: newWorkerId.trim() }),
            })
            const data = await res.json()
            if (res.ok) {
                setIssuedToken({ worker_id: data.worker_id, token: data.token })
                setNewWorkerId('')
                fetchWorkers()
            } else {
                setError(data.error || 'Failed to issue token')
            }
        } catch (err: any) {
            setError(err.message || 'Unknown error')
        } finally {
            setIssuing(false)
        }
    }

    const revokeToken = async (workerId: string, tokenPrefix: string | null) => {
        if (!confirm(`Revoke the active token for worker "${workerId}"? It will stop working immediately.`)) return
        // token_id isn't shown in this list view (only prefix); the revoke
        // route needs token_id, so this pulls the full token list first.
        const listRes = await authedFetch(token, '/api/admin/worker-tokens')
        const listData = await listRes.json()
        const match = (listData.tokens || []).find((t: any) => t.worker_id === workerId && !t.revoked_at)
        if (!match) {
            setError('No active token found to revoke')
            return
        }
        const res = await authedFetch(token, `/api/admin/worker-tokens/${match.token_id}`, { method: 'DELETE' })
        if (res.ok) fetchWorkers()
        else setError('Failed to revoke token')
    }

    return (
        <div className="container mx-auto p-4 max-w-6xl">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">AIR Workers</h1>
                <button
                    onClick={fetchWorkers}
                    disabled={loading}
                    className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium disabled:opacity-50"
                >
                    {loading ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>

            {error && (
                <div className="bg-red-50 text-red-500 p-4 rounded-md mb-6 border border-red-200">{error}</div>
            )}

            <div className="border rounded-lg p-4 mb-6">
                <h2 className="font-semibold mb-2">Issue a new Worker Token</h2>
                <div className="flex gap-2">
                    <input
                        className="border rounded px-3 py-2 text-sm flex-1"
                        placeholder="worker_id (e.g. air-worker-01)"
                        value={newWorkerId}
                        onChange={(e) => setNewWorkerId(e.target.value)}
                    />
                    <button
                        onClick={issueToken}
                        disabled={issuing || !newWorkerId.trim()}
                        className="px-4 py-2 rounded-md bg-green-600 text-white text-sm font-medium disabled:opacity-50"
                    >
                        {issuing ? 'Issuing...' : 'Issue token'}
                    </button>
                </div>
                {issuedToken && (
                    <div className="mt-3 bg-yellow-50 border border-yellow-300 rounded p-3 text-sm">
                        <strong>Token for {issuedToken.worker_id}</strong> (shown once, copy now):
                        <pre className="mt-1 break-all whitespace-pre-wrap select-all">{issuedToken.token}</pre>
                    </div>
                )}
            </div>

            <div className="border rounded-lg overflow-x-auto">
                <table className="min-w-full text-sm">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="text-left p-3">Worker ID</th>
                            <th className="text-left p-3">Group</th>
                            <th className="text-left p-3">Status</th>
                            <th className="text-left p-3">Last Heartbeat</th>
                            <th className="text-left p-3">Token</th>
                            <th className="text-left p-3">Current Job</th>
                            <th className="text-left p-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {workers.map((w) => (
                            <tr key={w.worker_id} className="border-t">
                                <td className="p-3 font-mono">{w.worker_id}</td>
                                <td className="p-3">{w.worker_group}</td>
                                <td className="p-3">
                                    <span className={w.online ? 'text-green-600' : 'text-gray-400'}>
                                        {w.online ? 'online' : 'offline'}
                                    </span>
                                </td>
                                <td className="p-3">{formatDate(w.last_heartbeat_at)}</td>
                                <td className="p-3">
                                    {w.token_revoked ? (
                                        <span className="text-red-500">revoked</span>
                                    ) : (
                                        <span className="font-mono">{w.token_prefix}...</span>
                                    )}
                                </td>
                                <td className="p-3">
                                    {w.current_job ? (
                                        <span>
                                            {w.current_job.worker_status || w.current_job.status} ({w.current_job.progress}%)
                                            {w.current_job.retry_count ? ` retries=${w.current_job.retry_count}` : ''}
                                            {w.current_job.error_code ? ` [${w.current_job.error_code}]` : ''}
                                        </span>
                                    ) : (
                                        <span className="text-gray-400">idle</span>
                                    )}
                                </td>
                                <td className="p-3">
                                    {!w.token_revoked && (
                                        <button
                                            onClick={() => revokeToken(w.worker_id, w.token_prefix)}
                                            className="text-red-600 text-xs underline"
                                        >
                                            Revoke token
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                        {workers.length === 0 && !loading && (
                            <tr>
                                <td colSpan={7} className="p-6 text-center text-gray-400">
                                    No workers registered yet
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
