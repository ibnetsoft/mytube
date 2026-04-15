
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'

// 관리자 이메일 목록
const ADMIN_EMAILS = ['ejsh0519@naver.com']

type Tab = 'users' | 'queue'

type AiLog = {
    id: number
    task_type: string
    model_id: string
    provider: string
    status: string
    prompt_summary: string
    error_msg: string
    elapsed_time: number
    created_at: string
}

type ApiKeySet = {
    gemini: string
    youtube: string
    elevenlabs: string
    topview: string
    topview_uid: string
}

const EMPTY_KEYS: ApiKeySet = {
    gemini: '', youtube: '', elevenlabs: '', topview: '', topview_uid: ''
}

const KEY_LABELS: Record<keyof ApiKeySet, string> = {
    gemini: '✨ Gemini API Key',
    youtube: '▶️ YouTube Data API Key',
    elevenlabs: '🎙️ ElevenLabs API Key',
    topview: '🛒 TopView API Key',
    topview_uid: '🛒 TopView UID',
}

export default function AdminDashboardContent() {
    const router = useRouter()
    const { t } = useLanguage()
    const [users, setUsers] = useState<any[]>([])
    const [requests, setRequests] = useState<any[]>([])
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [isAdmin, setIsAdmin] = useState(false)
    const [activeTab, setActiveTab] = useState<Tab>('users')
    const [selectedUser, setSelectedUser] = useState<any | null>(null)
    const [apiKeys, setApiKeys] = useState<ApiKeySet>(EMPTY_KEYS)
    const [savingKeys, setSavingKeys] = useState(false)
    const [keysSaved, setKeysSaved] = useState(false)
    const [logUser, setLogUser] = useState<any | null>(null)
    const [logs, setLogs] = useState<AiLog[]>([])
    const [logsLoading, setLogsLoading] = useState(false)

    useEffect(() => {
        const handleAuth = (session: any) => {
            if (!session?.user) {
                setLoading(false)
                setIsAdmin(false)
                return
            }

            const userEmail = session.user.email || ''
            if (ADMIN_EMAILS.includes(userEmail)) {
                setIsAdmin(true)
                fetchData()
            } else {
                setIsAdmin(false)
                setLoading(false)
            }
        }

        const initAuth = async () => {
            try {
                const { data: { session } } = await supabase.auth.getSession()
                handleAuth(session)
            } catch (e) {
                console.error('Auth init failed:', e)
                setLoading(false)
                setIsAdmin(false)
            }
        }

        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
            handleAuth(session)
        })

        initAuth()
        return () => subscription.unsubscribe()
    }, [])

    const fetchData = async () => {
        setLoading(true)
        await Promise.all([fetchUsers(), fetchRequests()])
        setLoading(false)
    }

    const fetchUsers = async () => {
        try {
            const res = await fetch('/api/admin/users')
            const data = await res.json()
            if (data.users) {
                setUsers(data.users)
            }
        } catch (e) {
            console.error("유저 목록 로딩 실패", e)
        }
    }

    const fetchRequests = async () => {
        try {
            const res = await fetch('/api/admin/publishing')
            const data = await res.json()
            if (data.requests) {
                setRequests(data.requests)
            }
        } catch (e) {
            console.error("발행 요청 로딩 실패", e)
        }
    }

    const toggleMembership = async (userId: string, currentRole: string) => {
        const nextRole = currentRole === 'independent' ? 'standard' : 'independent'
        try {
            const res = await fetch('/api/admin/users/role', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, role: nextRole })
            })
            const data = await res.json()
            if (data.success) {
                setUsers(users.map(u =>
                    u.id === userId ? { ...u, app_metadata: { ...u.app_metadata, membership: nextRole } } : u
                ))
            }
        } catch (e) {
            console.error("등급 변경 실패", e)
        }
    }

    const openUserPanel = (user: any) => {
        setSelectedUser(user)
        setKeysSaved(false)
        // Load existing keys from user_metadata
        const meta = user.user_metadata || {}
        setApiKeys({
            gemini: meta.gemini_api_key || '',
            youtube: meta.youtube_api_key || '',
            elevenlabs: meta.elevenlabs_api_key || '',
            topview: meta.topview_api_key || '',
            topview_uid: meta.topview_uid || '',
        })
    }

    const saveUserApiKeys = async () => {
        if (!selectedUser) return
        setSavingKeys(true)
        setKeysSaved(false)
        try {
            const res = await fetch(`/api/admin/users/${selectedUser.id}/settings`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(apiKeys)
            })
            if (res.ok) {
                setKeysSaved(true)
                // Update local state so re-open shows latest values
                setUsers(users.map(u =>
                    u.id === selectedUser.id
                        ? { ...u, user_metadata: {
                            ...(u.user_metadata || {}),
                            gemini_api_key: apiKeys.gemini,
                            youtube_api_key: apiKeys.youtube,
                            elevenlabs_api_key: apiKeys.elevenlabs,
                            topview_api_key: apiKeys.topview,
                            topview_uid: apiKeys.topview_uid,
                        }}
                        : u
                ))
            }
        } catch (e) {
            console.error('API 키 저장 실패', e)
        } finally {
            setSavingKeys(false)
        }
    }

    const updateRequestStatus = async (requestId: string, status: string) => {
        try {
            const res = await fetch('/api/admin/publishing', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ requestId, status })
            })
            const data = await res.json()
            if (data.success) {
                setRequests(requests.map(r => r.id === requestId ? { ...r, status } : r))
            }
        } catch (e) {
            console.error("상태 변경 실패", e)
        }
    }

    const openLogViewer = async (user: any, e: React.MouseEvent) => {
        e.stopPropagation()
        setLogUser(user)
        setLogs([])
        setLogsLoading(true)
        try {
            const res = await fetch(`/api/admin/users/${user.id}/logs`)
            const data = await res.json()
            setLogs(data.logs || [])
        } catch (e) {
            console.error('로그 로딩 실패', e)
        } finally {
            setLogsLoading(false)
        }
    }

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return '-'
        const d = new Date(dateStr)
        const year = d.getFullYear()
        const month = String(d.getMonth() + 1).padStart(2, '0')
        const day = String(d.getDate()).padStart(2, '0')
        return `${year}-${month}-${day}`
    }

    if (loading) return <div className="text-white p-10 text-center bg-gray-900 min-h-screen font-bold tracking-widest animate-pulse">{t.loading}</div>

    if (!isAdmin) {
        return (
            <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center justify-center p-4">
                <h1 className="text-2xl font-bold mb-4 text-red-500">🛡️ No Admin Access</h1>
                <p className="text-gray-400 mb-8 text-center text-sm">
                    You do not have permission to view this page.<br />
                    Please log in with an administrator account.
                </p>
                <button
                    onClick={() => router.push('/')}
                    className="px-6 py-3 bg-red-600 hover:bg-red-700 rounded-lg font-bold transition shadow-lg"
                >
                    Go to Login
                </button>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-gray-950 text-white p-8 font-sans">
            {/* Log Viewer Modal */}
            {logUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setLogUser(null)} />
                    <div className="relative w-full max-w-5xl bg-gray-900 border border-white/10 rounded-3xl shadow-2xl flex flex-col max-h-[85vh]">
                        {/* Header */}
                        <div className="p-6 border-b border-white/10 flex justify-between items-center flex-shrink-0">
                            <div>
                                <h3 className="font-black text-lg text-white flex items-center gap-2">
                                    📊 AI 생성 로그
                                </h3>
                                <p className="text-xs text-gray-400 mt-1">{logUser.email}</p>
                            </div>
                            <div className="flex items-center gap-4">
                                {/* Stats */}
                                {!logsLoading && logs.length > 0 && (
                                    <div className="flex gap-3 text-[10px] font-black">
                                        <span className="bg-white/5 px-3 py-1.5 rounded-xl">
                                            TOTAL <span className="text-white ml-1">{logs.length}</span>
                                        </span>
                                        <span className="bg-green-500/10 text-green-400 px-3 py-1.5 rounded-xl">
                                            SUCCESS <span className="ml-1">{logs.filter(l => l.status === 'success').length}</span>
                                        </span>
                                        <span className="bg-red-500/10 text-red-400 px-3 py-1.5 rounded-xl">
                                            FAILED <span className="ml-1">{logs.filter(l => l.status === 'failed').length}</span>
                                        </span>
                                        <span className="bg-blue-500/10 text-blue-400 px-3 py-1.5 rounded-xl">
                                            AVG {(logs.reduce((a, l) => a + (l.elapsed_time || 0), 0) / logs.length).toFixed(1)}s
                                        </span>
                                    </div>
                                )}
                                <button onClick={() => setLogUser(null)} className="text-gray-500 hover:text-white text-xl leading-none">✕</button>
                            </div>
                        </div>
                        {/* Table */}
                        <div className="overflow-y-auto flex-1">
                            {logsLoading ? (
                                <div className="flex items-center justify-center py-24 text-gray-500 font-black text-xs uppercase tracking-widest animate-pulse">
                                    로딩 중...
                                </div>
                            ) : logs.length === 0 ? (
                                <div className="flex items-center justify-center py-24 text-gray-600 font-black text-xs uppercase tracking-widest">
                                    로그 없음 — 아직 생성 기록이 없습니다
                                </div>
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
                                        {logs.map(log => {
                                            const d = new Date(log.created_at)
                                            const timeStr = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
                                            const dateStr = `${String(d.getMonth()+1).padStart(2,'0')}. ${String(d.getDate()).padStart(2,'0')}.`
                                            return (
                                                <tr key={log.id} className="hover:bg-white/5 transition-all">
                                                    <td className="px-6 py-3 font-mono text-gray-400 whitespace-nowrap">
                                                        <div className="font-bold text-white">{timeStr}</div>
                                                        <div className="text-[10px] text-gray-600">{dateStr}</div>
                                                    </td>
                                                    <td className="px-6 py-3">
                                                        <span className={`px-2 py-1 rounded-lg font-black uppercase text-[10px] ${log.task_type === 'image' ? 'bg-pink-500/15 text-pink-400' : log.task_type === 'video' ? 'bg-purple-500/15 text-purple-400' : 'bg-blue-500/15 text-blue-400'}`}>
                                                            {log.task_type}
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-3 font-mono text-gray-300 whitespace-nowrap">
                                                        <div className="text-[11px] font-bold">{log.model_id}</div>
                                                        <div className="text-[9px] text-gray-600 uppercase">{log.provider}</div>
                                                    </td>
                                                    <td className="px-6 py-3 text-gray-400 max-w-xs truncate italic">
                                                        &ldquo;{log.prompt_summary}&rdquo;
                                                        {log.status === 'failed' && log.error_msg && (
                                                            <div className="text-red-400 text-[10px] mt-0.5 not-italic truncate">{log.error_msg}</div>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-3 text-right font-mono font-bold whitespace-nowrap">
                                                        <span className={log.elapsed_time > 20 ? 'text-orange-400' : 'text-gray-300'}>
                                                            {log.elapsed_time?.toFixed(1)}s
                                                        </span>
                                                    </td>
                                                    <td className="px-6 py-3 text-center">
                                                        {log.status === 'success' ? (
                                                            <span className="bg-green-500/15 text-green-400 border border-green-500/20 px-3 py-1 rounded-full font-black text-[10px] uppercase">SUCCESS</span>
                                                        ) : (
                                                            <span className="bg-red-500/15 text-red-400 border border-red-500/20 px-3 py-1 rounded-full font-black text-[10px] uppercase">FAILED</span>
                                                        )}
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

            {/* User API Key Panel (Side Drawer) */}
            {selectedUser && (
                <div className="fixed inset-0 z-50 flex">
                    {/* Backdrop */}
                    <div className="flex-1 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedUser(null)} />
                    {/* Drawer */}
                    <div className="w-full max-w-md bg-gray-900 border-l border-white/10 shadow-2xl flex flex-col overflow-y-auto">
                        <div className="p-6 border-b border-white/10 flex justify-between items-start">
                            <div>
                                <h3 className="font-black text-lg text-white">🔑 API 키 관리</h3>
                                <p className="text-xs text-gray-400 mt-1 break-all">{selectedUser.email}</p>
                                <span className={`text-[10px] px-2 py-0.5 rounded-full font-black uppercase mt-1 inline-block ${selectedUser.app_metadata?.membership === 'independent' ? 'bg-purple-500/20 text-purple-400' : 'bg-blue-500/20 text-blue-400'}`}>
                                    {selectedUser.app_metadata?.membership || 'standard'}
                                </span>
                            </div>
                            <button onClick={() => setSelectedUser(null)} className="text-gray-500 hover:text-white text-xl leading-none">✕</button>
                        </div>

                        <div className="p-6 flex-1 space-y-4">
                            <p className="text-xs text-gray-500 leading-relaxed">
                                아래 키를 입력하면 해당 유저의 로컬 앱에서 Supabase 인증 후 자동으로 사용됩니다.
                                빈 칸으로 저장하면 해당 키가 제거됩니다.
                            </p>

                            {(Object.keys(EMPTY_KEYS) as (keyof ApiKeySet)[]).map(key => (
                                <div key={key}>
                                    <label className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1 block">
                                        {KEY_LABELS[key]}
                                    </label>
                                    <input
                                        type="password"
                                        value={apiKeys[key]}
                                        onChange={e => setApiKeys(prev => ({ ...prev, [key]: e.target.value }))}
                                        onFocus={e => (e.target as HTMLInputElement).type = 'text'}
                                        onBlur={e => (e.target as HTMLInputElement).type = 'password'}
                                        placeholder={apiKeys[key] ? '••••••••••••' : '(미설정)'}
                                        className="w-full bg-black/40 border border-white/10 text-xs px-4 py-2.5 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                    />
                                </div>
                            ))}
                        </div>

                        <div className="p-6 border-t border-white/10">
                            {keysSaved && (
                                <p className="text-xs text-green-400 font-bold mb-3 text-center">✅ 저장 완료</p>
                            )}
                            <button
                                onClick={saveUserApiKeys}
                                disabled={savingKeys}
                                className="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-black rounded-2xl transition-all text-sm"
                            >
                                {savingKeys ? '저장 중...' : '💾 키 저장하기'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <div className="max-w-7xl mx-auto">
                <div className="flex justify-between items-center mb-10">
                    <h1 className="text-3xl font-black bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent flex items-center gap-3 italic">
                        PICADIRI ADMIN
                    </h1>
                    <div className="flex items-center gap-6">
                        <LanguageSelector />
                        <button onClick={() => router.push('/dashboard')} className="text-xs font-bold text-gray-500 hover:text-white flex items-center gap-2 transition-all group">
                            <span className="group-hover:-translate-x-1 transition-transform">←</span> {t.backToDashboard}
                        </button>
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex gap-4 mb-8">
                    <button
                        onClick={() => setActiveTab('users')}
                        className={`px-6 py-3 rounded-2xl font-black text-sm transition-all ${activeTab === 'users' ? 'bg-blue-600 text-white shadow-lg' : 'bg-white/5 text-gray-500 hover:bg-white/10'}`}
                    >
                        {t.userManagement}
                    </button>
                    <button
                        onClick={() => setActiveTab('queue')}
                        className={`px-6 py-3 rounded-2xl font-black text-sm transition-all flex items-center gap-2 ${activeTab === 'queue' ? 'bg-purple-600 text-white shadow-lg' : 'bg-white/5 text-gray-500 hover:bg-white/10'}`}
                    >
                        {t.publishingQueue}
                        {requests.filter(r => r.status === 'pending').length > 0 && (
                            <span className="bg-red-500 text-white text-[10px] px-2 py-0.5 rounded-full animate-bounce">
                                {requests.filter(r => r.status === 'pending').length}
                            </span>
                        )}
                    </button>
                </div>

                {activeTab === 'users' ? (
                    <div className="bg-[#111] rounded-[2.5rem] border border-white/5 overflow-hidden shadow-2xl">
                        <div className="p-8 border-b border-white/5 bg-white/5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                            <h2 className="font-black text-xl tracking-tight uppercase">{t.userManagement}</h2>
                            <div className="w-full sm:w-auto">
                                <input
                                    type="text"
                                    placeholder={t.searchEmail}
                                    className="w-full sm:w-64 bg-black/40 border border-white/10 text-xs px-5 py-3 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all placeholder:text-gray-700 font-bold"
                                />
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm">
                                <thead className="bg-black/40 text-gray-500 font-black h-16 uppercase text-[10px] tracking-widest">
                                    <tr>
                                        <th className="px-10 py-3">{t.emailId}</th>
                                        <th className="px-10 py-3">{t.joinDate}</th>
                                        <th className="px-10 py-3">{t.lastLogin}</th>
                                        <th className="px-10 py-3 text-center">{t.membership}</th>
                                        <th className="px-10 py-3 text-center">{t.manage}</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5 font-medium">
                                    {users.map((user) => (
                                        <tr key={user.id} className="hover:bg-white/5 transition-all h-24 cursor-pointer" onClick={() => openUserPanel(user)}>
                                            <td className="px-10 py-4">
                                                <div className="font-bold text-white text-base tracking-tight">{user.email}</div>
                                                <div className="text-[10px] text-gray-600 font-mono mt-1 opacity-70 tracking-tighter truncate max-w-[200px]">{user.id}</div>
                                            </td>
                                            <td className="px-10 py-4 text-gray-400">
                                                {formatDate(user.created_at)}
                                            </td>
                                            <td className="px-10 py-4 text-gray-400">
                                                {formatDate(user.last_sign_in_at)}
                                            </td>
                                            <td className="px-10 py-4 text-center">
                                                <div className="flex flex-col items-center gap-1">
                                                    <button
                                                        onClick={() => toggleMembership(user.id, user.app_metadata?.membership || 'standard')}
                                                        className={`px-4 py-1.5 rounded-xl text-[10px] font-black border transition-all uppercase tracking-tighter flex items-center gap-2 group/btn ${user.app_metadata?.membership === 'independent'
                                                            ? 'bg-purple-500/10 text-purple-500 border-purple-500/20 hover:bg-purple-500/20 hover:border-purple-500/40'
                                                            : 'bg-blue-500/10 text-blue-500 border-blue-500/20 hover:bg-blue-500/20 hover:border-blue-500/40'
                                                            }`}
                                                        title="클릭하여 등급 변경"
                                                    >
                                                        <span>{user.app_metadata?.membership === 'independent' ? '💎 ' + t.independent : '👤 ' + t.standard}</span>
                                                        <span className="opacity-0 group-hover/btn:opacity-100 transition-opacity text-[8px] bg-white/10 px-1 rounded">CHANGE</span>
                                                    </button>
                                                </div>
                                            </td>
                                            <td className="px-10 py-4 text-center">
                                                <div className="flex justify-center gap-2">
                                                    <button
                                                        onClick={(e) => openLogViewer(user, e)}
                                                        className="text-blue-400/80 hover:text-blue-300 hover:bg-blue-500/10 text-[10px] border border-blue-500/20 px-3 py-2 rounded-xl transition-all font-black uppercase tracking-tighter"
                                                    >
                                                        📊 로그
                                                    </button>
                                                    <button className="text-red-500/80 hover:text-red-400 hover:bg-red-500/10 text-[10px] border border-red-500/20 px-3 py-2 rounded-xl transition-all font-black uppercase tracking-tighter">
                                                        {t.ban}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                    {users.length === 0 && (
                                        <tr>
                                            <td colSpan={5} className="px-10 py-32 text-center text-gray-600 font-black uppercase tracking-widest text-xs italic">
                                                {t.noData}
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                ) : (
                    <div className="bg-[#111] rounded-[2.5rem] border border-white/5 overflow-hidden shadow-2xl">
                        <div className="p-8 border-b border-white/5 bg-white/5 flex justify-between items-center">
                            <h2 className="font-black text-xl tracking-tight uppercase">{t.publishingQueue}</h2>
                            <button
                                onClick={fetchData}
                                className="px-4 py-2 bg-white/5 hover:bg-white/10 rounded-xl text-xs font-bold transition-all flex items-center gap-2 border border-white/10"
                            >
                                🔄 {t.loading === "로딩 중..." ? "새로고침" : "Refresh"}
                            </button>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-left text-sm">
                                <thead className="bg-black/40 text-gray-500 font-black h-16 uppercase text-[10px] tracking-widest">
                                    <tr>
                                        <th className="px-10 py-3">{t.videoTitle}</th>
                                        <th className="px-10 py-3">{t.requestDate}</th>
                                        <th className="px-10 py-3 text-center">{t.status}</th>
                                        <th className="px-10 py-3 text-center">{t.manage}</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5 font-medium">
                                    {requests.map((request) => (
                                        <tr key={request.id} className="hover:bg-white/5 transition-all h-24">
                                            <td className="px-10 py-4">
                                                <div className="font-bold text-white text-base tracking-tight">{request.metadata?.title || 'Untitled Video'}</div>
                                                <div className="text-[10px] text-gray-600 font-mono mt-1 opacity-70 tracking-tighter">{request.profiles?.email}</div>
                                            </td>
                                            <td className="px-10 py-4 text-gray-400">
                                                {formatDate(request.created_at)}
                                            </td>
                                            <td className="px-10 py-4 text-center">
                                                <span className={`px-3 py-1 rounded-full text-[10px] font-black border uppercase tracking-tighter ${request.status === 'pending' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' :
                                                    request.status === 'approved' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20' :
                                                        request.status === 'published' ? 'bg-green-500/10 text-green-500 border-green-500/20' :
                                                            request.status === 'to_be_published' ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' :
                                                                'bg-red-500/10 text-red-500 border-red-500/20'
                                                    }`}>
                                                    {t[request.status as keyof typeof t] || request.status}
                                                </span>
                                            </td>
                                            <td className="px-10 py-4 text-center">
                                                <div className="flex justify-center gap-3">
                                                    {request.status === 'pending' && (
                                                        <>
                                                            <button
                                                                onClick={() => updateRequestStatus(request.id, 'approved')}
                                                                className="text-blue-500/80 hover:text-blue-400 hover:bg-blue-500/10 text-[10px] border border-blue-500/20 px-3 py-2 rounded-xl transition-all font-black uppercase tracking-tighter"
                                                            >
                                                                {t.approve}
                                                            </button>
                                                            <button
                                                                onClick={() => updateRequestStatus(request.id, 'rejected')}
                                                                className="text-red-500/80 hover:text-red-400 hover:bg-red-500/10 text-[10px] border border-red-500/20 px-3 py-2 rounded-xl transition-all font-black uppercase tracking-tighter"
                                                            >
                                                                {t.reject}
                                                            </button>
                                                        </>
                                                    )}
                                                    {request.status === 'approved' && (
                                                        <button
                                                            onClick={() => updateRequestStatus(request.id, 'to_be_published')}
                                                            className="bg-green-600 hover:bg-green-500 text-white text-[10px] px-4 py-2 rounded-xl transition-all font-black uppercase tracking-tighter shadow-lg shadow-green-900/20"
                                                        >
                                                            {t.publishToYoutube}
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => setPreviewUrl(request.video_url)}
                                                        className="text-gray-400 hover:text-white text-[10px] border border-white/10 px-3 py-2 rounded-xl transition-all font-black uppercase tracking-tighter"
                                                    >
                                                        {t.viewVideo}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                    {requests.length === 0 && (
                                        <tr>
                                            <td colSpan={4} className="px-10 py-32 text-center text-gray-600 font-black uppercase tracking-widest text-xs italic">
                                                {t.noRequests}
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </div>

            {/* Video Preview Modal */}
            {previewUrl && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div
                        className="absolute inset-0 bg-black/90 backdrop-blur-xl"
                        onClick={() => setPreviewUrl(null)}
                    />
                    <div className="relative bg-[#111] border border-white/10 rounded-[2.5rem] overflow-hidden max-w-5xl w-full shadow-2xl animate-in zoom-in duration-300">
                        <div className="p-6 border-b border-white/5 flex justify-between items-center bg-white/5">
                            <h3 className="font-black uppercase tracking-tighter text-gray-400">Video Preview</h3>
                            <button
                                onClick={() => setPreviewUrl(null)}
                                className="w-10 h-10 flex items-center justify-center rounded-full bg-white/5 hover:bg-white/10 transition-all text-xl"
                            >
                                ✕
                            </button>
                        </div>
                        <div className="aspect-video bg-black">
                            <video
                                src={previewUrl}
                                controls
                                autoPlay
                                className="w-full h-full"
                            />
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
