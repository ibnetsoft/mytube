'use client'

import { useCallback, useEffect, useState } from 'react'

const LOCAL_APP_ORIGINS = ['http://127.0.0.1:8001', 'http://localhost:8001']

type AdminFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

type LearningStatsPanelProps = {
    adminFetch: AdminFetch
    refreshLabel: string
}

function StatCard({ label, value, unit, color, subLabel }: { label: string; value: string | number; unit: string; color: string; subLabel?: string }) {
    const textColor = color === 'green' ? 'text-[#22c55e]' : color === 'orange' ? 'text-[#f97316]' : color === 'blue' ? 'text-blue-400' : 'text-white'
    return (
        <div className="bg-[#0f172a]/60 border border-white/20 p-6 rounded-2xl flex flex-col justify-center min-h-[110px] relative overflow-hidden group hover:border-blue-500/40 transition-all shadow-lg">
            <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                <div className={`w-12 h-12 rounded-full ${color === 'green' ? 'bg-green-500' : color === 'orange' ? 'bg-orange-500' : 'bg-blue-500'}`} />
            </div>
            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1">{label}</span>
            <div className="flex items-baseline gap-2">
                <span className={`text-3xl font-black tabular-nums ${textColor}`}>{value}</span>
                <span className="text-[10px] text-gray-500 font-bold uppercase">{unit}</span>
            </div>
            {subLabel && <div className="text-[9px] text-gray-600 font-bold mt-1 uppercase">{subLabel}</div>}
        </div>
    )
}

export default function LearningStatsPanel({ adminFetch, refreshLabel }: LearningStatsPanelProps) {
    const [learningStats, setLearningStats] = useState<any>(null)
    const [learningLoading, setLearningLoading] = useState(false)
    const [learningError, setLearningError] = useState('')

    const fetchLearningStats = useCallback(async () => {
        setLearningLoading(true)
        setLearningError('')
        try {
            const remoteRes = await adminFetch('/api/admin/learning?limit=100', { method: 'GET' })
            if (remoteRes.ok) {
                const data = await remoteRes.json()
                setLearningStats(data.stats || data)
                return
            }

            let loaded: any = null
            let lastError = `Remote HTTP ${remoteRes.status}`
            for (const origin of LOCAL_APP_ORIGINS) {
                try {
                    const res = await fetch(`${origin}/api/admin/learning/stats?limit=100`, { method: 'GET' })
                    if (!res.ok) {
                        lastError = `HTTP ${res.status}`
                        continue
                    }
                    const data = await res.json()
                    loaded = data.stats || data
                    break
                } catch (err: any) {
                    lastError = err?.message || String(err)
                }
            }
            if (!loaded) {
                setLearningError(lastError || 'Learning API is not available.')
                setLearningStats(null)
                return
            }
            setLearningStats(loaded)
        } finally {
            setLearningLoading(false)
        }
    }, [adminFetch])

    useEffect(() => {
        fetchLearningStats()
    }, [fetchLearningStats])

    return (
        <div className="space-y-8 animate-in fade-in duration-300">
            <div className="bg-[#0f172a]/60 rounded-[2.5rem] border border-white/10 p-8 shadow-2xl">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="font-black text-2xl tracking-tight flex items-center gap-2">🧠 학습 데이터 통계</h2>
                        <p className="text-xs text-gray-500 mt-1">Supabase에 동기화된 제작/검수/업로드 학습 로그를 집계합니다. 원격 데이터가 없으면 로컬 앱(8001)을 보조 조회합니다.</p>
                    </div>
                    <button onClick={fetchLearningStats} className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-black uppercase tracking-widest">
                        {learningLoading ? 'Loading...' : refreshLabel}
                    </button>
                </div>

                {learningError && (
                    <div className="mb-6 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-5 py-4 text-sm text-amber-200">
                        학습 통계를 불러올 수 없습니다. Supabase 스키마 적용 여부와 로컬 앱(127.0.0.1:8001) 실행 상태를 확인하세요. ({learningError})
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4 mb-8">
                    <StatCard label="Learning Events" value={learningStats?.total_events || 0} unit="logs" color="blue" subLabel="전체 이벤트" />
                    <StatCard label="Snapshots" value={learningStats?.total_snapshots || 0} unit="sets" color="green" subLabel="상태 스냅샷" />
                    <StatCard label="Reviews" value={learningStats?.manual_review_count || 0} unit="notes" color="orange" subLabel="검수 메모" />
                    <StatCard label="Avg Rating" value={learningStats?.average_rating ?? '-'} unit="/5" color="green" subLabel="수동 평점" />
                    <StatCard label="QA Holds" value={learningStats?.qa_hold_count || 0} unit="hold" color="orange" subLabel="업로드 보류" />
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-5">
                        <h3 className="text-sm font-black mb-4">이벤트 유형 TOP</h3>
                        <div className="space-y-2">
                            {(learningStats?.event_counts || []).slice(0, 10).map((row: any) => (
                                <div key={row.event_type} className="flex items-center justify-between text-xs rounded-xl bg-white/5 px-3 py-2">
                                    <span className="font-bold text-gray-300">{String(row.event_type).replace(/_/g, ' ')}</span>
                                    <span className="font-black text-blue-300">{row.count}</span>
                                </div>
                            ))}
                            {(!learningStats?.event_counts || learningStats.event_counts.length === 0) && <div className="text-xs text-gray-500">아직 이벤트가 없습니다.</div>}
                        </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-black/20 p-5">
                        <h3 className="text-sm font-black mb-4">단계별 로그</h3>
                        <div className="space-y-2">
                            {(learningStats?.stage_counts || []).slice(0, 10).map((row: any) => (
                                <div key={row.stage || 'unknown'} className="flex items-center justify-between text-xs rounded-xl bg-white/5 px-3 py-2">
                                    <span className="font-bold text-gray-300">{row.stage || 'unknown'}</span>
                                    <span className="font-black text-emerald-300">{row.count}</span>
                                </div>
                            ))}
                            {(!learningStats?.stage_counts || learningStats.stage_counts.length === 0) && <div className="text-xs text-gray-500">아직 단계별 데이터가 없습니다.</div>}
                        </div>
                    </div>

                    <div className="rounded-2xl border border-white/10 bg-black/20 p-5">
                        <h3 className="text-sm font-black mb-4">최근 프로젝트</h3>
                        <div className="space-y-2 max-h-[320px] overflow-y-auto">
                            {(learningStats?.projects || []).slice(0, 12).map((p: any) => (
                                <div key={p.project_id} className="text-xs rounded-xl bg-white/5 px-3 py-2">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="font-bold text-white truncate">#{p.project_id} {p.name || 'Untitled'}</span>
                                        <span className="text-blue-300 font-black">{p.event_count}</span>
                                    </div>
                                    <div className="text-[10px] text-gray-500 truncate">{p.topic || '-'}</div>
                                </div>
                            ))}
                            {(!learningStats?.projects || learningStats.projects.length === 0) && <div className="text-xs text-gray-500">아직 프로젝트 데이터가 없습니다.</div>}
                        </div>
                    </div>
                </div>

                <div className="mt-8 rounded-2xl border border-white/10 bg-black/20 overflow-hidden">
                    <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
                        <h3 className="text-sm font-black">최근 학습 로그</h3>
                        <span className="text-[10px] text-gray-500">Local App Learning Events</span>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                            <thead className="text-gray-500 uppercase bg-white/5">
                                <tr>
                                    <th className="px-4 py-3">Time</th>
                                    <th className="px-4 py-3">Project</th>
                                    <th className="px-4 py-3">Stage</th>
                                    <th className="px-4 py-3">Event</th>
                                    <th className="px-4 py-3">Note / Payload</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                                {(learningStats?.recent_events || []).slice(0, 50).map((event: any) => {
                                    const payload = event.payload || {}
                                    const note = payload.note || payload.title || payload.thumbnail_style || payload.error || payload.youtube_video_id || ''
                                    return (
                                        <tr key={event.id} className="hover:bg-white/5">
                                            <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{event.created_at || '-'}</td>
                                            <td className="px-4 py-3 text-gray-300 whitespace-nowrap">#{event.project_id} {event.project_name || ''}</td>
                                            <td className="px-4 py-3 text-blue-300 font-bold">{event.stage || '-'}</td>
                                            <td className="px-4 py-3 text-white font-black">{String(event.event_type || '').replace(/_/g, ' ')}</td>
                                            <td className="px-4 py-3 text-gray-400 max-w-[520px] truncate" title={JSON.stringify(payload)}>{String(note || JSON.stringify(payload || {})).slice(0, 180)}</td>
                                        </tr>
                                    )
                                })}
                                {(!learningStats?.recent_events || learningStats.recent_events.length === 0) && (
                                    <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">아직 학습 로그가 없습니다.</td></tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    )
}
