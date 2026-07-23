'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'

// [TTS 에러 리포팅] 유저 앱에서 발생하는 TTS 생성 실패를 웹어드민에서 조회하기 위한
// 페이지. 기존 /api/admin/logs(ai_logs 테이블)를 그대로 재사용한다 - 별도 테이블/파이프라인을
// 새로 만들지 않고, app/routers/tts.py가 db.add_ai_log()로 남기는 로그를 그대로 노출한다.
// DashboardContent.tsx에도 로그 테이블이 있지만 error_msg(에러 메시지)와 worker_email(누가)
// 컬럼이 없어 "누가 어떤 에러를 받았는지" 확인이 불가능했다 - 이 페이지가 그 간극을 메운다.

type LogRow = {
    id: string
    user_id: string | null
    worker_email: string | null
    task_type: string | null
    provider: string | null
    model_id: string | null
    status: string | null
    error_msg: string | null
    prompt_summary: string | null
    elapsed_time: number | null
    created_at: string
}

const DAY_OPTIONS = [1, 3, 7, 30]

export default function AdminLogsPage() {
    const [logs, setLogs] = useState<LogRow[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [days, setDays] = useState(7)
    const [taskType, setTaskType] = useState('tts')
    const [status, setStatus] = useState('failed')
    const [search, setSearch] = useState('')

    const fetchLogs = useCallback(async (rangeDays: number) => {
        setLoading(true)
        setError('')
        try {
            const { data: { session } } = await supabase.auth.getSession()
            const token = session?.access_token
            const res = await fetch(`/api/admin/logs?days=${rangeDays}`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            })
            const data = await res.json()
            if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
            setLogs(data.logs || [])
        } catch (e: any) {
            setError(e.message || '로그를 불러오지 못했습니다.')
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchLogs(days)
    }, [fetchLogs, days])

    const taskTypes = useMemo(() => {
        const set = new Set<string>()
        logs.forEach(l => { if (l.task_type) set.add(l.task_type) })
        return Array.from(set).sort()
    }, [logs])

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase()
        return logs.filter(l => {
            if (taskType !== 'all' && (l.task_type || '') !== taskType) return false
            if (status !== 'all' && (l.status || '').toLowerCase() !== status) return false
            if (q) {
                const haystack = `${l.worker_email || ''} ${l.error_msg || ''} ${l.prompt_summary || ''} ${l.user_id || ''}`.toLowerCase()
                if (!haystack.includes(q)) return false
            }
            return true
        })
    }, [logs, taskType, status, search])

    return (
        <div className="min-h-screen bg-gray-950 text-white">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <h1 className="text-2xl font-bold">에러 로그 조회</h1>
                    <button
                        onClick={() => fetchLogs(days)}
                        disabled={loading}
                        className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium disabled:opacity-50"
                    >
                        {loading ? '불러오는 중...' : '새로고침'}
                    </button>
                </div>

                <div className="flex flex-wrap items-center gap-3 bg-gray-900 border border-gray-800 p-4 rounded-lg">
                    <select
                        value={days}
                        onChange={e => setDays(Number(e.target.value))}
                        className="bg-black/40 border border-gray-700 rounded-md px-3 py-2 text-sm"
                    >
                        {DAY_OPTIONS.map(d => (
                            <option key={d} value={d}>최근 {d}일</option>
                        ))}
                    </select>

                    <select
                        value={taskType}
                        onChange={e => setTaskType(e.target.value)}
                        className="bg-black/40 border border-gray-700 rounded-md px-3 py-2 text-sm"
                    >
                        <option value="all">모든 기능</option>
                        <option value="tts">TTS</option>
                        {taskTypes.filter(t => t !== 'tts').map(t => (
                            <option key={t} value={t}>{t}</option>
                        ))}
                    </select>

                    <select
                        value={status}
                        onChange={e => setStatus(e.target.value)}
                        className="bg-black/40 border border-gray-700 rounded-md px-3 py-2 text-sm"
                    >
                        <option value="all">모든 상태</option>
                        <option value="failed">실패만</option>
                        <option value="success">성공만</option>
                    </select>

                    <input
                        type="text"
                        placeholder="이메일 / 에러 메시지 검색..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className="bg-black/40 border border-gray-700 rounded-md px-3 py-2 text-sm flex-1 min-w-[200px]"
                    />

                    <span className="text-xs text-gray-400 whitespace-nowrap">{filtered.length}건</span>
                </div>

                {error && (
                    <div className="bg-red-950/50 text-red-400 p-4 rounded-md border border-red-900">
                        {error}
                    </div>
                )}

                <div className="border border-gray-800 rounded-lg overflow-hidden overflow-x-auto">
                    <table className="w-full text-sm text-left min-w-[900px]">
                        <thead className="text-xs text-gray-400 uppercase bg-gray-900">
                            <tr>
                                <th className="px-4 py-3">시간</th>
                                <th className="px-4 py-3">사용자</th>
                                <th className="px-4 py-3">기능</th>
                                <th className="px-4 py-3">엔진/모델</th>
                                <th className="px-4 py-3">상태</th>
                                <th className="px-4 py-3">에러 메시지</th>
                                <th className="px-4 py-3 text-right">소요시간</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-800">
                            {filtered.length === 0 && !loading && (
                                <tr>
                                    <td colSpan={7} className="px-4 py-10 text-center text-gray-500">
                                        조건에 맞는 로그가 없습니다.
                                    </td>
                                </tr>
                            )}
                            {filtered.map(log => (
                                <tr key={log.id} className="hover:bg-gray-900/60">
                                    <td className="px-4 py-3 whitespace-nowrap text-gray-300">
                                        {new Date(log.created_at).toLocaleString()}
                                    </td>
                                    <td className="px-4 py-3">
                                        <div className="font-medium">{log.worker_email || '알 수 없음'}</div>
                                        {log.user_id && (
                                            <div className="text-[10px] text-gray-500">{log.user_id}</div>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 uppercase text-xs font-semibold">{log.task_type}</td>
                                    <td className="px-4 py-3">
                                        <div>{log.model_id}</div>
                                        <div className="text-[10px] text-gray-500 uppercase">{log.provider}</div>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`px-2 py-1 rounded text-xs font-semibold ${(log.status || '').toLowerCase() === 'success' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                                            {(log.status || '').toUpperCase() || 'UNKNOWN'}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 max-w-[360px]">
                                        <span className="text-red-300 text-xs break-words">{log.error_msg || '-'}</span>
                                    </td>
                                    <td className="px-4 py-3 text-right text-gray-400 whitespace-nowrap">
                                        {log.elapsed_time ? `${log.elapsed_time.toFixed(1)}s` : '-'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    )
}
