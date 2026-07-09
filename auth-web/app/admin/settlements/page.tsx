'use client'

import { useEffect, useState } from 'react'

export default function SettlementsPage() {
    const [settlements, setSettlements] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [processingId, setProcessingId] = useState<string | null>(null)

    useEffect(() => {
        fetchSettlements()
    }, [])

    const fetchSettlements = async () => {
        setLoading(true)
        setError('')
        try {
            const res = await fetch('/api/admin/settlements')
            const data = await res.json()
            if (data.success) {
                setSettlements(data.data)
            } else {
                setError(data.error || 'Failed to fetch settlements')
            }
        } catch (err: any) {
            setError(err.message || 'Unknown error')
        } finally {
            setLoading(false)
        }
    }

    const handlePayout = async (id: string) => {
        if (!confirm('Are you sure you want to approve and pay this commission? This will increase the user\'s USDT balance.')) {
            return
        }

        setProcessingId(id)
        setError('')
        try {
            const res = await fetch('/api/admin/settlements/payout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ commission_id: id })
            })
            const data = await res.json()
            if (data.success) {
                // Refresh the list after successful payout
                fetchSettlements()
            } else {
                setError(data.error || 'Failed to process payout')
            }
        } catch (err: any) {
            setError(err.message || 'Unknown error during payout')
        } finally {
            setProcessingId(null)
        }
    }

    return (
        <div className="container mx-auto p-4 max-w-6xl">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold">Referral Settlements</h1>
                <button
                    onClick={fetchSettlements}
                    disabled={loading}
                    className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium disabled:opacity-50"
                >
                    {loading ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>

            {error && (
                <div className="bg-red-50 text-red-500 p-4 rounded-md mb-6 border border-red-200">
                    {error}
                </div>
            )}

            <div className="border rounded-lg">
                <div className="p-4 border-b">
                    <h2 className="text-lg font-semibold">Settlement History</h2>
                </div>
                <div className="p-4">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs text-gray-700 uppercase bg-gray-50">
                                <tr>
                                    <th className="px-4 py-3">Date</th>
                                    <th className="px-4 py-3">Type</th>
                                    <th className="px-4 py-3">Beneficiary</th>
                                    <th className="px-4 py-3">Source User</th>
                                    <th className="px-4 py-3">Base Amount</th>
                                    <th className="px-4 py-3">Rate</th>
                                    <th className="px-4 py-3">Commission</th>
                                    <th className="px-4 py-3">Status</th>
                                    <th className="px-4 py-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {settlements.length === 0 && !loading && (
                                    <tr>
                                        <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                                            No settlements found.
                                        </td>
                                    </tr>
                                )}
                                {settlements.map((s) => (
                                    <tr key={s.id} className="border-b">
                                        <td className="px-4 py-3">{new Date(s.created_at).toLocaleString()}</td>
                                        <td className="px-4 py-3 font-semibold">{s.commission_type}</td>
                                        <td className="px-4 py-3">
                                            <div>{s.beneficiary?.email || 'Unknown'}</div>
                                            <div className="text-xs text-gray-400">{s.beneficiary_id}</div>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div>{s.source?.email || 'Unknown'}</div>
                                            <div className="text-xs text-gray-400">{s.source_user_id}</div>
                                        </td>
                                        <td className="px-4 py-3">{s.base_tokens}</td>
                                        <td className="px-4 py-3">{s.rate_percent}%</td>
                                        <td className="px-4 py-3 font-bold text-green-600">{s.commission_tokens}</td>
                                        <td className="px-4 py-3">
                                            <span className={`px-2 py-1 rounded text-xs font-semibold ${s.status === 'pending' ? 'bg-yellow-100 text-yellow-800' : s.status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                                                {s.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            {s.status === 'pending' && (
                                                <button
                                                    onClick={() => handlePayout(s.id)}
                                                    disabled={processingId === s.id}
                                                    className="px-3 py-1.5 rounded-md bg-blue-600 text-white text-xs font-medium disabled:opacity-50"
                                                >
                                                    {processingId === s.id ? 'Processing...' : 'Approve & Pay'}
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    )
}
