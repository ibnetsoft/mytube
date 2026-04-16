
'use client'

import { useEffect, useState, useCallback } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'

interface UserProfile {
    id: string
    email: string
    created_at: string
    last_sign_in_at: string | null
    user_metadata: Record<string, any>
    app_metadata: Record<string, any>
}

interface ApiKeyState {
    gemini: string
    youtube: string
    elevenlabs: string
    topview: string
    topview_uid: string
    youtube_channel?: string
    youtube_handle?: string
}

const ADMIN_EMAIL = 'ejsh0519@naver.com'

function formatDate(dateStr: string | null | undefined) {
    if (!dateStr) return '-'
    const d = new Date(dateStr)
    return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`
}

function StatCard({ label, value, icon, accent }: { label: string; value: string | number; icon: string; accent: string }) {
    return (
        <div className={`relative bg-[#111] border border-white/5 rounded-2xl p-5 flex items-center gap-4 hover:border-${accent}-500/30 transition-all duration-300 group`}>
            <div className={`w-12 h-12 rounded-xl bg-${accent}-500/10 flex items-center justify-center text-2xl flex-shrink-0 group-hover:scale-110 transition-transform`}>
                {icon}
            </div>
            <div>
                <p className="text-xs text-gray-500 uppercase tracking-widest font-bold mb-1">{label}</p>
                <p className="text-2xl font-black text-white">{value}</p>
            </div>
        </div>
    )
}

export default function DashboardContent() {
    const router = useRouter()
    const { t } = useLanguage()
    const [user, setUser] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [users, setUsers] = useState<UserProfile[]>([])
    const [usersLoading, setUsersLoading] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [selectedUser, setSelectedUser] = useState<UserProfile | null>(null)
    const [copied, setCopied] = useState(false)
    const [apiKeys, setApiKeys] = useState<ApiKeyState>({ gemini: '', youtube: '', elevenlabs: '', topview: '', topview_uid: '', youtube_channel: '', youtube_handle: '' })
    const [apiSaved, setApiSaved] = useState(false)
    const [showApiPanel, setShowApiPanel] = useState(false)
    const [userApiKeys, setUserApiKeys] = useState<ApiKeyState>({ gemini: '', youtube: '', elevenlabs: '', topview: '', topview_uid: '', youtube_channel: '', youtube_handle: '' })
    const [savingUserApi, setSavingUserApi] = useState(false)
    const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'api'>('overview')
    const [logViewUser, setLogViewUser] = useState<UserProfile | null>(null)
    const [logs, setLogs] = useState<any[]>([])
    const [logsLoading, setLogsLoading] = useState(false)

    // ─── Auth Check ──────────────────────────────────────────
    useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => {
            if (!session) router.push('/')
            else setUser(session.user)
            setLoading(false)
        })
    }, [router])

    const isAdmin = user?.email === ADMIN_EMAIL

    // ─── Log Viewer ──────────────────────────────────────────
    const openLogViewer = async (u: UserProfile, e: React.MouseEvent) => {
        e.stopPropagation()
        setLogViewUser(u)
        setLogs([])
        setLogsLoading(true)
        try {
            const res = await fetch(`/api/admin/users/${u.id}/logs`)
            const data = await res.json()
            setLogs(data.logs || [])
        } catch (err) {
            console.error('로그 로딩 실패', err)
        } finally {
            setLogsLoading(false)
        }
    }

    // ─── Fetch User List (admin only) ────────────────────────
    const fetchUsers = useCallback(async () => {
        if (!isAdmin) return
        setUsersLoading(true)
        try {
            const res = await fetch('/api/admin/users')
            const data = await res.json()
            if (data.users) setUsers(data.users)
        } catch (e) {
            console.error(e)
        } finally {
            setUsersLoading(false)
        }
    }, [isAdmin])

    useEffect(() => {
        if (isAdmin && activeTab === 'users') fetchUsers()
    }, [isAdmin, activeTab, fetchUsers])

    // API 탭 진입 시 기존 키 로드
    useEffect(() => {
        if (isAdmin && activeTab === 'api' && user?.id) {
            fetch(`/api/admin/settings?userId=${user.id}`)
                .then(r => r.json())
                .then(data => {
                    if (!data.error) {
                        setApiKeys({
                            gemini:      data.gemini_val      || '',
                            youtube:     data.youtube_val     || '',
                            elevenlabs:  data.elevenlabs_val  || '',
                            topview:     data.topview_val     || '',
                            topview_uid: data.topview_uid_val || '',
                        })
                    }
                })
                .catch(console.error)
        }
    }, [isAdmin, activeTab, user?.id])

    const handleSignOut = async () => {
        await supabase.auth.signOut()
        router.push('/')
    }

    const handleCopyKey = () => {
        navigator.clipboard.writeText(user?.id || '')
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
    }

    const handleSaveApiKeys = async () => {
        setUsersLoading(true)
        try {
            // 1. Save to Local Python App (Runtime Sync)
            try {
                await fetch('http://localhost:8000/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        gemini_api_key: apiKeys.gemini,
                        youtube_api_key: apiKeys.youtube,
                        elevenlabs_api_key: apiKeys.elevenlabs,
                        topview_api_key: apiKeys.topview,
                        topview_uid: apiKeys.topview_uid,
                    })
                })
            } catch (localErr) {
                console.warn('Local app sync failed (Is it running?):', localErr)
            }

            // 2. Save to Supabase via admin settings API
            const res = await fetch('/api/admin/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId: user?.id, ...apiKeys })
            })
            
            if (res.ok) {
                setApiSaved(true)
                setTimeout(() => setApiSaved(false), 2500)
            } else {
                throw new Error('Failed to save to dashboard')
            }
        } catch (e) {
            console.error(e)
            alert('설정 저장 중 오류가 발생했습니다.')
        } finally {
            setUsersLoading(false)
        }
    }

    const filteredUsers = users.filter(u =>
        u.email?.toLowerCase().includes(searchQuery.toLowerCase())
    )

    if (loading) return (
        <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
                <div className="w-10 h-10 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
                <p className="text-gray-500 font-medium tracking-widest text-sm animate-pulse">{t.loading}</p>
            </div>
        </div>
    )

    const thisMonthUsers = users.filter(u => {
        const d = new Date(u.created_at)
        const now = new Date()
        return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
    }).length

    return (
        <div className="min-h-screen bg-[#050505] text-white font-sans selection:bg-blue-500/30">

            {/* ── Log Viewer Modal ── */}
            {logViewUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setLogViewUser(null)} />
                    <div className="relative w-full max-w-5xl bg-[#111] border border-white/10 rounded-3xl shadow-2xl flex flex-col max-h-[85vh]">
                        <div className="p-6 border-b border-white/10 flex justify-between items-center flex-shrink-0">
                            <div>
                                <h3 className="font-black text-lg text-white">📊 AI 생성 로그</h3>
                                <p className="text-xs text-gray-400 mt-1">{logViewUser.email}</p>
                            </div>
                            <div className="flex items-center gap-3">
                                {!logsLoading && logs.length > 0 && (
                                    <div className="flex gap-2 text-[10px] font-black">
                                        <span className="bg-white/5 px-3 py-1.5 rounded-xl">TOTAL <span className="text-white ml-1">{logs.length}</span></span>
                                        <span className="bg-green-500/10 text-green-400 px-3 py-1.5 rounded-xl">SUCCESS <span className="ml-1">{logs.filter((l:any) => l.status === 'success').length}</span></span>
                                        <span className="bg-red-500/10 text-red-400 px-3 py-1.5 rounded-xl">FAILED <span className="ml-1">{logs.filter((l:any) => l.status !== 'success').length}</span></span>
                                        <span className="bg-blue-500/10 text-blue-400 px-3 py-1.5 rounded-xl">AVG {logs.length ? (logs.reduce((a:number,l:any)=>a+(l.elapsed_time||0),0)/logs.length).toFixed(1) : 0}s</span>
                                    </div>
                                )}
                                <button onClick={() => setLogViewUser(null)} className="text-gray-500 hover:text-white text-xl leading-none ml-2">✕</button>
                            </div>
                        </div>
                        <div className="overflow-y-auto flex-1">
                            {logsLoading ? (
                                <div className="flex items-center justify-center py-24 text-gray-500 font-black text-xs uppercase tracking-widest animate-pulse">로딩 중...</div>
                            ) : logs.length === 0 ? (
                                <div className="flex items-center justify-center py-24 text-gray-600 font-black text-xs uppercase tracking-widest">로그 없음 — 아직 생성 기록이 없습니다</div>
                            ) : (
                                <table className="w-full text-left text-xs">
                                    <thead className="bg-black/40 text-gray-500 font-black uppercase tracking-widest sticky top-0">
                                        <tr>
                                            <th className="px-6 py-3">TIME</th>
                                            <th className="px-6 py-3">TASK</th>
                                            <th className="px-6 py-3">MODEL</th>
                                            <th className="px-6 py-3">PROMPT SUMMARY</th>
                                            <th className="px-6 py-3 text-right">DURATION</th>
                                            <th className="px-6 py-3 text-center">STATUS</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5">
                                        {logs.map((log: any) => {
                                            const d = new Date(log.created_at)
                                            const timeStr = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
                                            const dateStr = `${String(d.getMonth()+1).padStart(2,'0')}. ${String(d.getDate()).padStart(2,'0')}.`
                                            return (
                                                <tr key={log.id} className="hover:bg-white/5 transition-all">
                                                    <td className="px-6 py-3 font-mono whitespace-nowrap">
                                                        <div className="font-bold text-white">{timeStr}</div>
                                                        <div className="text-[10px] text-gray-600">{dateStr}</div>
                                                    </td>
                                                    <td className="px-6 py-3">
                                                        <span className={`px-2 py-1 rounded-lg font-black uppercase text-[10px] ${log.task_type === 'image' ? 'bg-pink-500/15 text-pink-400' : log.task_type === 'video' ? 'bg-purple-500/15 text-purple-400' : 'bg-blue-500/15 text-blue-400'}`}>
                                                            {log.task_type}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-3 font-mono whitespace-nowrap">
                                                        <div className="text-[11px] font-bold text-gray-300">{log.model_id}</div>
                                                        <div className="text-[9px] text-gray-600 uppercase">{log.provider}</div>
                                                    </td>
                                                    <td className="px-6 py-3 text-gray-400 max-w-xs">
                                                        <div className="truncate italic">&ldquo;{log.prompt_summary}&rdquo;</div>
                                                        {log.status !== 'success' && log.error_msg && (
                                                            <div className="text-red-400 text-[10px] mt-0.5 truncate not-italic">{log.error_msg}</div>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-3 text-right font-mono font-bold whitespace-nowrap">
                                                        <span className={log.elapsed_time > 20 ? 'text-orange-400' : 'text-gray-300'}>{(log.elapsed_time||0).toFixed(1)}s</span>
                                                    </td>
                                                    <td className="px-6 py-3 text-center">
                                                        {log.status === 'success'
                                                            ? <span className="bg-green-500/15 text-green-400 border border-green-500/20 px-3 py-1 rounded-full font-black text-[10px] uppercase">SUCCESS</span>
                                                            : <span className="bg-red-500/15 text-red-400 border border-red-500/20 px-3 py-1 rounded-full font-black text-[10px] uppercase">FAILED</span>
                                                        }
                                                    </td>
                                                </tr>
                                            )
                                        })}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* ── Top Nav ── */}
            <nav className="sticky top-0 z-50 border-b border-white/5 bg-black/70 backdrop-blur-xl px-6 py-3">
                <div className="max-w-7xl mx-auto flex justify-between items-center">
                    <span className="text-xl font-black bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent italic tracking-tighter">
                        PICADIRI STUDIO
                    </span>
                    <div className="flex gap-4 items-center">
                        <LanguageSelector />
                        <div className="hidden md:flex flex-col items-end">
                            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-tighter">Authenticated as</span>
                            <span className="text-xs font-medium text-blue-400">{user?.email}</span>
                        </div>
                        {isAdmin && (
                            <span className="px-3 py-1 text-[10px] font-black bg-red-500/10 text-red-400 border border-red-500/20 rounded-full uppercase tracking-widest">
                                ADMIN
                            </span>
                        )}
                        <button onClick={handleSignOut} className="px-4 py-2 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-all font-bold text-gray-300">
                            {t.logout}
                        </button>
                    </div>
                </div>
            </nav>

            <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">

                {/* ── Page Header ── */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h2 className="text-3xl font-extrabold text-white/90 tracking-tight">
                            {isAdmin ? '🛡️ 사용자 관리 대시보드' : t.helloCreator}
                        </h2>
                        <p className="text-gray-500 text-sm mt-1">
                            {isAdmin ? '전체 사용자 현황 및 API 관리' : '내 계정 정보를 확인하세요.'}
                        </p>
                    </div>
                    {/* Tab Switcher */}
                    <div className="flex gap-2 bg-white/5 border border-white/10 rounded-2xl p-1">
                        {(['overview', ...(isAdmin ? ['users', 'api'] : [])] as const).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab as any)}
                                className={`px-5 py-2 rounded-xl text-sm font-bold transition-all ${activeTab === tab
                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/30'
                                    : 'text-gray-400 hover:text-white'
                                }`}
                            >
                                {tab === 'overview' ? '개요' : tab === 'users' ? '👥 사용자' : '🔑 API'}
                            </button>
                        ))}
                    </div>
                </div>

                {/* ══════════════════ OVERVIEW TAB ══════════════════ */}
                {activeTab === 'overview' && (
                    <div className="space-y-8">

                        {/* Stats Row (admin only) */}
                        {isAdmin && (
                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                                <StatCard label="전체 사용자" value={users.length || '—'} icon="👥" accent="blue" />
                                <StatCard label="이번 달 가입" value={thisMonthUsers || '—'} icon="📈" accent="green" />
                                <StatCard label="활성 플랜" value="Pro" icon="⭐" accent="purple" />
                                <StatCard label="최신 버전" value="v2.0.1" icon="✅" accent="indigo" />
                            </div>
                        )}

                        {/* My Info Cards */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

                            {/* Profile Card */}
                            <div className="bg-[#111] border border-white/5 hover:border-blue-500/30 transition-all duration-500 rounded-3xl p-8 group relative overflow-hidden">
                                <div className="absolute top-4 right-4 text-5xl opacity-5 group-hover:opacity-15 group-hover:scale-125 group-hover:rotate-12 transition-all duration-700">👤</div>
                                <p className="text-xs uppercase font-black text-gray-500 tracking-widest mb-5">내 프로필</p>
                                <div className="space-y-4">
                                    <div>
                                        <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">사용자명</p>
                                        <p className="text-white font-bold">{user?.user_metadata?.full_name || user?.email?.split('@')[0] || '-'}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">이메일</p>
                                        <p className="text-blue-400 font-medium text-sm">{user?.email}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">시작일</p>
                                        <p className="text-white font-bold">{formatDate(user?.created_at)}</p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">마지막 로그인</p>
                                        <p className="text-white font-bold">{formatDate(user?.last_sign_in_at)}</p>
                                    </div>
                                    <div className="pt-1">
                                        <span className="text-xs font-black text-blue-400 px-3 py-1 bg-blue-500/10 rounded-full border border-blue-500/20">
                                            {user?.app_metadata?.membership === 'independent' ? '⭐ Pro Plan' : '✦ Standard Plan'}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* License Key Card */}
                            <div className="bg-[#111] border border-white/5 hover:border-yellow-500/30 transition-all duration-500 rounded-3xl p-8 group relative overflow-hidden">
                                <div className="absolute top-4 right-4 text-5xl opacity-5 group-hover:opacity-15 group-hover:scale-125 group-hover:rotate-12 transition-all duration-700">🔑</div>
                                <p className="text-xs uppercase font-black text-gray-500 tracking-widest mb-5">내 라이선스 키</p>
                                <div className="bg-black/60 border border-white/5 rounded-2xl p-4 font-mono text-yellow-400 text-sm break-all mb-6 leading-relaxed shadow-inner">
                                    {user?.id || '-'}
                                </div>
                                <button
                                    onClick={handleCopyKey}
                                    className={`w-full py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all active:scale-[0.98] ${copied
                                        ? 'bg-green-600 text-white shadow-lg shadow-green-900/30'
                                        : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-xl shadow-blue-900/20'
                                    }`}
                                >
                                    {copied ? '✓ 복사 완료!' : '🔑 키 복사하기'}
                                </button>
                            </div>

                            {/* Download + Quick Guide Card */}
                            <div className="bg-[#111] border border-white/5 hover:border-green-500/30 transition-all duration-500 rounded-3xl p-8 group relative overflow-hidden flex flex-col gap-6">
                                <div className="absolute top-4 right-4 text-5xl opacity-5 group-hover:opacity-15 group-hover:scale-125 group-hover:rotate-12 transition-all duration-700">🚀</div>
                                <div>
                                    <p className="text-xs uppercase font-black text-gray-500 tracking-widest mb-4">{t.downloadTitle}</p>
                                    <p className="text-sm text-gray-500 leading-relaxed mb-5">{t.downloadDesc}</p>
                                    <a
                                        href={user?.app_metadata?.membership === 'independent'
                                            ? 'https://drive.google.com/file/d/pro_link_placeholder'
                                            : 'https://drive.google.com/file/d/lite_link_placeholder'}
                                        target="_blank"
                                        className="flex items-center justify-center gap-2 w-full py-4 rounded-2xl font-black text-sm uppercase tracking-widest bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 shadow-xl shadow-green-900/20 active:scale-[0.98] transition-all"
                                    >
                                        📥 {user?.app_metadata?.membership === 'independent' ? t.downloadPro : t.downloadLite}
                                    </a>
                                </div>
                                <div className="border-t border-white/5 pt-5">
                                    <p className="text-xs uppercase font-black text-purple-400 tracking-widest mb-4">{t.guideTitle}</p>
                                    <ul className="space-y-3">
                                        {[t.guide1, t.guide2, t.guide3].map((g, i) => (
                                            <li key={i} className="flex gap-3 items-start text-sm text-gray-400">
                                                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-black flex items-center justify-center">
                                                    {i + 1}
                                                </span>
                                                <span className="pt-0.5">{g}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ══════════════════ USERS TAB (Admin Only) ══════════════════ */}
                {activeTab === 'users' && isAdmin && (
                    <div className="space-y-6">
                        {/* Search Bar */}
                        <div className="flex gap-4 items-center">
                            <div className="relative flex-1 max-w-sm">
                                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500">🔍</span>
                                <input
                                    type="text"
                                    placeholder={t.searchEmail}
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-all"
                                />
                            </div>
                            <button
                                onClick={fetchUsers}
                                className="px-5 py-3 bg-blue-600/20 hover:bg-blue-600/40 text-blue-400 border border-blue-500/20 rounded-xl text-sm font-bold transition-all"
                            >
                                새로고침
                            </button>
                            <span className="ml-auto text-gray-500 text-sm font-medium">
                                총 <span className="text-white font-black">{filteredUsers.length}</span>명
                            </span>
                        </div>

                        {/* Users Table */}
                        <div className="bg-[#111] border border-white/5 rounded-2xl overflow-hidden">
                            <div className="grid grid-cols-12 text-[10px] uppercase font-black text-gray-500 tracking-widest px-6 py-4 border-b border-white/5 bg-black/30">
                                <span className="col-span-3">이메일 / 사용자명</span>
                                <span className="col-span-2">라이선스 키 (ID)</span>
                                <span className="col-span-2">시작일</span>
                                <span className="col-span-2">마지막 로그인</span>
                                <span className="col-span-2">플랜</span>
                                <span className="col-span-1 text-right">관리</span>
                            </div>

                            {usersLoading ? (
                                <div className="flex items-center justify-center py-20 gap-3">
                                    <div className="w-6 h-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
                                    <p className="text-gray-500 text-sm">{t.loading}</p>
                                </div>
                            ) : filteredUsers.length === 0 ? (
                                <div className="text-center py-20 text-gray-600 font-medium">{t.noData}</div>
                            ) : (
                                <div className="divide-y divide-white/5">
                                    {filteredUsers.map(u => (
                                        <div
                                            key={u.id}
                                            className={`grid grid-cols-12 items-center px-6 py-4 hover:bg-white/[0.03] transition-colors cursor-pointer ${selectedUser?.id === u.id ? 'bg-blue-500/5 border-l-2 border-l-blue-500' : ''}`}
                                            onClick={() => setSelectedUser(selectedUser?.id === u.id ? null : u)}
                                        >
                                            <div className="col-span-3 min-w-0">
                                                <p className="text-sm font-bold text-white truncate">{u.email}</p>
                                                <p className="text-xs text-gray-500 truncate">{u.user_metadata?.full_name || '-'}</p>
                                            </div>
                                            <div className="col-span-2">
                                                <p className="text-xs font-mono text-yellow-500/80 truncate">{u.id.substring(0, 18)}…</p>
                                            </div>
                                            <div className="col-span-2">
                                                <p className="text-sm text-gray-300">{formatDate(u.created_at)}</p>
                                            </div>
                                            <div className="col-span-2">
                                                <p className="text-sm text-gray-300">{formatDate(u.last_sign_in_at)}</p>
                                            </div>
                                            <div className="col-span-2">
                                                <span className={`text-xs font-bold px-2 py-1 rounded-full border ${u.app_metadata?.membership === 'independent'
                                                    ? 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                                                    : 'bg-gray-500/10 text-gray-400 border-gray-500/20'
                                                    }`}>
                                                    {u.app_metadata?.membership === 'independent' ? '⭐ Pro' : '✦ Standard'}
                                                </span>
                                            </div>
                                            <div className="col-span-1 flex justify-end gap-1">
                                                <button
                                                    onClick={e => { e.stopPropagation(); navigator.clipboard.writeText(u.id); }}
                                                    className="px-2 py-1 text-[10px] bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/20 rounded-lg font-bold transition-all"
                                                    title="키 복사"
                                                >
                                                    복사
                                                </button>
                                            </div>

                                            {/* Expanded Detail Row */}
                                            {selectedUser?.id === u.id && (
                                                <div className="col-span-12 mt-4 bg-black/30 rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 gap-4 border border-white/5">
                                                    <div>
                                                        <p className="text-[10px] text-gray-600 uppercase tracking-widest mb-1">Full License Key</p>
                                                        <p className="text-xs font-mono text-yellow-400 break-all">{u.id}</p>
                                                    </div>
                                                    <div>
                                                        <p className="text-[10px] text-gray-600 uppercase tracking-widest mb-1">Provider</p>
                                                        <p className="text-xs text-white font-bold">{u.app_metadata?.provider || 'email'}</p>
                                                    </div>
                                                    <div>
                                                        <p className="text-[10px] text-gray-600 uppercase tracking-widest mb-1">Role</p>
                                                        <p className="text-xs text-white font-bold">{u.app_metadata?.role || 'user'}</p>
                                                    </div>
                                                    <div className="flex items-end gap-2">
                                                        <button
                                                            onClick={e => openLogViewer(u, e)}
                                                            className="px-3 py-2 text-xs bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/20 rounded-lg font-bold transition-all"
                                                        >
                                                            📊 로그
                                                        </button>
                                                        <button
                                                            onClick={e => {
                                                                e.stopPropagation();
                                                                    setUserApiKeys({
                                                                        gemini: u.user_metadata?.gemini_api_key || '',
                                                                        youtube: u.user_metadata?.youtube_api_key || '',
                                                                        elevenlabs: u.user_metadata?.elevenlabs_api_key || '',
                                                                        topview: u.user_metadata?.topview_api_key || '',
                                                                        topview_uid: u.user_metadata?.topview_uid || '',
                                                                        youtube_channel: u.user_metadata?.youtube_channel || '',
                                                                        youtube_handle: u.user_metadata?.youtube_handle || '',
                                                                    });
                                                                setShowApiPanel(!showApiPanel);
                                                            }}
                                                            className="px-3 py-2 text-xs bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 border border-blue-500/20 rounded-lg font-bold transition-all"
                                                        >
                                                            🔑 API 관리
                                                        </button>
                                                        <button
                                                            onClick={e => e.stopPropagation()}
                                                            className="px-3 py-2 text-xs bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 border border-purple-500/20 rounded-lg font-bold transition-all"
                                                        >
                                                            ✏️ 등급 전환
                                                        </button>
                                                        <button
                                                            onClick={e => e.stopPropagation()}
                                                            className="px-3 py-2 text-xs bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg font-bold transition-all"
                                                        >
                                                            🚫 차단
                                                        </button>
                                                    </div>

                                                    {/* User-Specific API Edit Panel */}
                                                    {showApiPanel && (
                                                        <div className="col-span-12 mt-4 pt-4 border-t border-white/5 space-y-4">
                                                            <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest">이 유저 전용 API 키 설정</p>
                                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                                    { label: '✨ Gemini API Key', key: 'gemini' as const, type: 'password' },
                                                                    { label: '▶️ YouTube Data API Key', key: 'youtube' as const, type: 'password' },
                                                                    { label: '🎙️ ElevenLabs API Key', key: 'elevenlabs' as const, type: 'password' },
                                                                    { label: '🛒 TopView API Key', key: 'topview' as const, type: 'password' },
                                                                    { label: '🛒 TopView UID', key: 'topview_uid' as const, type: 'password' },
                                                                    { label: '📺 YouTube 채널명', key: 'youtube_channel' as const, type: 'text' },
                                                                    { label: '📺 YouTube 핸들 (@)', key: 'youtube_handle' as const, type: 'text' },
                                                                ]).map(({ label, key, type }) => (
                                                                    <div key={key}>
                                                                        <label className="text-[9px] text-gray-500 block mb-1">{label}</label>
                                                                        <input
                                                                            type={type}
                                                                            value={userApiKeys[key]}
                                                                            onChange={e => setUserApiKeys({ ...userApiKeys, [key]: e.target.value })}
                                                                            className="w-full px-3 py-2 bg-black/50 border border-white/10 rounded-lg text-xs font-mono text-blue-300 focus:outline-none focus:border-blue-500/50"
                                                                            placeholder={`${label} 입력...`}
                                                                        />
                                                                    </div>
                                                                ))}
                                                            </div>
                                                            <div className="flex justify-end">
                                                                <button
                                                                    onClick={async (e) => {
                                                                        e.stopPropagation();
                                                                        setSavingUserApi(true);
                                                                        try {
                                                                            const res = await fetch(`/api/admin/users/${u.id}/settings`, {
                                                                                method: 'POST',
                                                                                headers: { 'Content-Type': 'application/json' },
                                                                                body: JSON.stringify(userApiKeys)
                                                                            });
                                                                            if (res.ok) alert('저장되었습니다.');
                                                                            else alert('저장 실패');
                                                                        } catch (err) { console.error(err); }
                                                                        setSavingUserApi(false);
                                                                    }}
                                                                    disabled={savingUserApi}
                                                                    className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all disabled:opacity-50"
                                                                >
                                                                    {savingUserApi ? '저장 중...' : '해당 유저 키 업데이트'}
                                                                </button>
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* ══════════════════ API TAB (Admin Only) ══════════════════ */}
                {activeTab === 'api' && isAdmin && (
                    <div className="max-w-2xl space-y-6">
                        <div className="bg-[#111] border border-white/5 rounded-3xl p-8 space-y-6">
                            <div>
                                <p className="text-xs uppercase font-black text-gray-500 tracking-widest mb-1">API 관리</p>
                                <p className="text-sm text-gray-600">서비스에 사용될 API 키를 안전하게 관리합니다.</p>
                            </div>

                            {[
                                { label: 'Google Gemini API Key', key: 'gemini' as const, icon: '✨', placeholder: 'AIza...' },
                                { label: 'YouTube Data API Key', key: 'youtube' as const, icon: '▶️', placeholder: 'AIza...' },
                                { label: 'ElevenLabs API Key', key: 'elevenlabs' as const, icon: '🎙️', placeholder: 'sk_...' },
                                { label: 'TopView API Key', key: 'topview' as const, icon: '🛒', placeholder: 'topview-...' },
                                { label: 'TopView UID', key: 'topview_uid' as const, icon: '🛒', placeholder: 'uid-...' },
                            ].map(({ label, key, icon, placeholder }) => (
                                <div key={key} className="border border-white/5 rounded-2xl p-5 hover:border-blue-500/20 transition-all">
                                    <div className="flex items-center gap-2 mb-3">
                                        <span className="text-base">{icon}</span>
                                        <label className="text-sm font-bold text-white/80">{label}</label>
                                    </div>
                                    <input
                                        type="password"
                                        placeholder={placeholder}
                                        value={apiKeys[key]}
                                        onChange={e => setApiKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/5 rounded-xl text-sm font-mono text-gray-300 placeholder-gray-700 focus:outline-none focus:border-blue-500/40 transition-all"
                                    />
                                </div>
                            ))}

                            <button
                                onClick={handleSaveApiKeys}
                                className={`w-full py-4 rounded-2xl font-black text-sm uppercase tracking-widest transition-all active:scale-[0.98] ${apiSaved
                                    ? 'bg-green-600 text-white shadow-lg shadow-green-900/30'
                                    : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-xl shadow-blue-900/20'
                                }`}
                            >
                                {apiSaved ? '✓ 저장 완료!' : '💾 API 키 저장'}
                            </button>
                        </div>

                        <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-2xl p-5">
                            <p className="text-xs font-black text-yellow-500 uppercase tracking-widest mb-2">⚠️ 보안 안내</p>
                            <p className="text-xs text-yellow-500/60 leading-relaxed">
                                API 키는 암호화되어 저장됩니다. 절대로 타인과 공유하지 마세요.
                                이 페이지는 관리자만 접근 가능합니다.
                            </p>
                        </div>
                    </div>
                )}

            </main>
        </div>
    )
}
