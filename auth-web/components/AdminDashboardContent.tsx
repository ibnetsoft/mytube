
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'

// 관리자 이메일 목록
const ADMIN_EMAILS = ['ejsh0519@naver.com']

type Tab = 'users' | 'queue' | 'categories'

type Category = {
    id: number
    name: string
    keywords: string
    benchmark_channel_url: string
    assigned_employee_email: string
    created_at: string
}

type TopicItem = {
    id: number
    category_id: number
    topic: string
    assigned_employee_email: string
    status: 'pending' | 'assigned' | 'completed'
    created_at: string
}

type AiLog = {
    id: number
    task_type: string
    model_id: string
    provider: string
    status: string
    prompt_summary: string
    error_msg: string
    elapsed_time: number
    input_tokens: number
    output_tokens: number
    thinking_tokens?: number
    balance_after?: number
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
    const [currentPeriod, setCurrentPeriod] = useState(1) // Default to Daily

    // Pagination & Sorting for Logs
    const [logSortOrder, setLogSortOrder] = useState<'newest' | 'oldest'>('newest')
    const [logPageSize, setLogPageSize] = useState(20)
    const [logCurrentPage, setLogCurrentPage] = useState(1)

    // 토큰 내역
    const [txUser, setTxUser] = useState<any | null>(null)
    const [transactions, setTransactions] = useState<any[]>([])
    const [txLoading, setTxLoading] = useState(false)

    // 카테고리 & AI 주제 자판기 상태
    const [categories, setCategories] = useState<Category[]>([])
    const [topics, setTopics] = useState<TopicItem[]>([])
    const [categoriesLoading, setCategoriesLoading] = useState(false)
    const [newCatName, setNewCatName] = useState('')
    const [newCatKeywords, setNewCatKeywords] = useState('')
    const [newCatChannel, setNewCatChannel] = useState('')
    const [newCatEmployee, setNewCatEmployee] = useState('')
    const [newCatScriptStyle, setNewCatScriptStyle] = useState('default')
    const [newCatImageStyle, setNewCatImageStyle] = useState('realistic')
    const [generatingCatId, setGeneratingCatId] = useState<number | null>(null)

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
        await Promise.all([fetchUsers(), fetchRequests(), fetchCategories(), fetchTopics()])
        setLoading(false)
    }

    const fetchCategories = async () => {
        try {
            setCategoriesLoading(true)
            const res = await fetch('/api/admin/categories')
            const data = await res.json()
            if (data.categories) setCategories(data.categories)
        } catch (e) {
            console.error("Failed to load categories:", e)
        } finally {
            setCategoriesLoading(false)
        }
    }

    const fetchTopics = async () => {
        try {
            const res = await fetch('/api/admin/topics-queue')
            const data = await res.json()
            if (data.topics) setTopics(data.topics)
        } catch (e) {
            console.error("Failed to load topics:", e)
        }
    }

    const handleCreateCategory = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!newCatName || !newCatEmployee) {
            alert('카테고리명과 담당 직원 이메일은 필수입니다.')
            return
        }
        try {
            const res = await fetch('/api/admin/categories', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: newCatName,
                    keywords: newCatKeywords,
                    benchmark_channel_url: newCatChannel,
                    assigned_employee_email: newCatEmployee,
                    default_script_style: newCatScriptStyle,
                    default_image_style: newCatImageStyle
                })
            })
            const data = await res.json()
            if (data.success) {
                setNewCatName('')
                setNewCatKeywords('')
                setNewCatChannel('')
                setNewCatEmployee('')
                setNewCatScriptStyle('default')
                setNewCatImageStyle('realistic')
                fetchCategories()
                fetchTopics()
                alert('카테고리가 성공적으로 등록되었으며, 기본 샘플 주제 3개가 적재되었습니다.')
            } else {
                alert('카테고리 등록 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('서버 등록 에러 발생')
        }
    }

    const handleDeleteCategory = async (id: number) => {
        if (!confirm('정말 이 카테고리를 삭제하시겠습니까? 관련 데이터도 함께 삭제될 수 있습니다.')) return
        try {
            const res = await fetch(`/api/admin/categories?id=${id}`, {
                method: 'DELETE'
            })
            const data = await res.json()
            if (data.success) {
                fetchCategories()
                fetchTopics()
            } else {
                alert('삭제 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
        }
    }

    const handleTriggerAiTopics = async (catId: number) => {
        setGeneratingCatId(catId)
        try {
            const res = await fetch('/api/admin/topics-queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ categoryId: catId })
            })
            const data = await res.json()
            if (data.success) {
                fetchTopics()
                alert(`AI가 새로운 세부 영상 주제 ${data.count}개를 성공적으로 생성하여 큐에 추가했습니다!`)
            } else {
                alert('AI 생성 실패: ' + data.error)
            }
        } catch (err) {
            console.error(err)
            alert('AI 생성 요청 오류')
        } finally {
            setGeneratingCatId(null)
        }
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
                body: JSON.stringify({ userId, membership: nextRole })
            })
            const data = await res.json()
            if (data.success) {
                setUsers(prev => prev.map(u =>
                    u.id === userId ? { ...u, app_metadata: { ...u.app_metadata, membership: nextRole } } : u
                ))
                alert(nextRole === 'independent' ? '💎 프로로 변경되었습니다.' : '👤 스탠다드로 변경되었습니다.')
            } else {
                alert('변경 실패: ' + (data.error || '서버 오류'))
            }
        } catch (e) {
            console.error("등급 변경 실패", e)
            alert('서버 통신 오류가 발생했습니다.')
        }
    }

    const [pinCode, setPinCode] = useState('1234')

    const openUserPanel = (user: any) => {
        setSelectedUser(user)
        setKeysSaved(false)
        setPinCode(user.profile?.pin_code || '1234')
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
                body: JSON.stringify({ ...apiKeys, pin_code: pinCode })
            })
            if (res.ok) {
                setKeysSaved(true)
                // Update local state so re-open shows latest values
                setUsers(users.map(u =>
                    u.id === selectedUser.id
                        ? { 
                            ...u, 
                            user_metadata: {
                                ...(u.user_metadata || {}),
                                gemini_api_key: apiKeys.gemini,
                                youtube_api_key: apiKeys.youtube,
                                elevenlabs_api_key: apiKeys.elevenlabs,
                                topview_api_key: apiKeys.topview,
                                topview_uid: apiKeys.topview_uid,
                            },
                            profile: {
                                ...(u.profile || {}),
                                pin_code: pinCode
                            }
                        }
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

    const rechargeTokens = async (userId: string) => {
        const amountStr = prompt("충전할 토큰 양을 입력하세요 (숫자만)", "1000000")
        if (!amountStr) return
        const amount = parseInt(amountStr)
        if (isNaN(amount) || amount <= 0) {
            alert("올바른 금액을 입력해주세요.")
            return
        }

        const description = prompt("충전 사유를 입력하세요 (예: 보상 지급, 정기 구독 등)", "관리자 충전")
        if (description === null) return; // Cancel

        try {
            const res = await fetch('/api/admin/users/recharge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, amount, description })
            })
            const data = await res.json()
            if (data.success) {
                setUsers(users.map(u =>
                    u.id === userId ? { ...u, profile: { ...u.profile, token_balance: (u.profile?.token_balance || 0) + amount } } : u
                ))
                alert(`성공적으로 ${amount.toLocaleString()} 토큰을 충전했습니다.`)
            } else {
                alert("충전 실패: " + data.error)
            }
        } catch (e) {
            console.error("충전 중 오류 발생", e)
            alert("서버 통신 오류가 발생했습니다.")
        }
    }

    const openLogViewer = async (user: any, days: number = 1, e?: React.MouseEvent) => {
        if (e) e.stopPropagation()
        setLogUser(user)
        setCurrentPeriod(days)
        setLogCurrentPage(1) // Reset pagination
        setLogs([])
        setLogsLoading(true)
        try {
            const res = await fetch(`/api/admin/users/${user.id}/logs?days=${days}`)
            const data = await res.json()
            setLogs(data.logs || [])
        } catch (e) {
            console.error('로그 로딩 실패', e)
        } finally {
            setLogsLoading(false)
        }
    }

    const openTxViewer = async (user: any, e?: React.MouseEvent) => {
        if (e) e.stopPropagation()
        setTxUser(user)
        setTransactions([])
        setTxLoading(true)
        try {
            const res = await fetch(`/api/admin/users/${user.id}/transactions?limit=50`)
            const data = await res.json()
            setTransactions(data.transactions || [])
        } catch (e) {
            console.error('토큰 내역 로딩 실패', e)
        } finally {
            setTxLoading(false)
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
            {/* Token Transaction Modal */}
            {txUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/80 backdrop-blur-md" onClick={() => setTxUser(null)} />
                    <div className="relative w-full max-w-2xl bg-gray-900 border border-white/10 rounded-[2.5rem] shadow-2xl flex flex-col max-h-[80vh] overflow-hidden">
                        {/* Header */}
                        <div className="p-6 border-b border-white/5 flex justify-between items-center flex-shrink-0">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 bg-gradient-to-br from-yellow-500 to-orange-600 rounded-xl flex items-center justify-center shadow-lg">
                                    <span className="text-lg">💰</span>
                                </div>
                                <div>
                                    <h3 className="font-black text-lg text-white tracking-tight">TOKEN HISTORY</h3>
                                    <p className="text-[11px] text-gray-400">{txUser.email}</p>
                                </div>
                            </div>
                            <button onClick={() => setTxUser(null)} className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/5 hover:bg-red-500/20 hover:text-red-500 border border-white/5 transition-all text-lg">✕</button>
                        </div>
                        {/* Body */}
                        <div className="overflow-y-auto flex-1 p-4">
                            {txLoading ? (
                                <div className="text-center text-gray-400 py-10 text-sm">로딩 중...</div>
                            ) : transactions.length === 0 ? (
                                <div className="text-center text-gray-500 py-10 text-sm">토큰 내역이 없습니다.</div>
                            ) : (
                                <table className="w-full text-xs">
                                    <thead>
                                        <tr className="text-[10px] font-black text-gray-500 uppercase tracking-widest border-b border-white/5">
                                            <th className="py-2 text-left">일시</th>
                                            <th className="py-2 text-center">구분</th>
                                            <th className="py-2 text-right">토큰</th>
                                            <th className="py-2 text-left pl-4">내용</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {transactions.map((tx: any) => (
                                            <tr key={tx.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                                                <td className="py-2 text-gray-400">{new Date(tx.created_at).toLocaleString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</td>
                                                <td className="py-2 text-center">
                                                    <span className={`px-2 py-0.5 rounded-md text-[10px] font-black ${tx.transaction_type === 'RECHARGE' ? 'bg-blue-500/20 text-blue-400' : tx.transaction_type === 'USAGE' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>
                                                        {tx.transaction_type === 'RECHARGE' ? '충전' : tx.transaction_type === 'USAGE' ? '차감' : tx.transaction_type}
                                                    </span>
                                                </td>
                                                <td className={`py-2 text-right font-black ${tx.amount > 0 ? 'text-blue-400' : 'text-red-400'}`}>
                                                    {tx.amount > 0 ? '+' : ''}{tx.amount.toLocaleString()}
                                                </td>
                                                <td className="py-2 pl-4 text-gray-400 truncate max-w-[160px]">{tx.description || '-'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* Log Viewer Modal */}
            {logUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div className="absolute inset-0 bg-black/80 backdrop-blur-md" onClick={() => setLogUser(null)} />
                    <div className="relative w-full max-w-6xl bg-gray-900 border border-white/10 rounded-[2.5rem] shadow-2xl flex flex-col max-h-[90vh] overflow-hidden">
                        {/* Header */}
                        <div className="p-8 border-b border-white/5 bg-white/[0.02] flex flex-col gap-6 flex-shrink-0">
                            <div className="flex justify-between items-start">
                                <div className="flex items-center gap-4">
                                    <div className="w-14 h-14 bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-900/40">
                                        <span className="text-2xl">📊</span>
                                    </div>
                                    <div>
                                        <h3 className="font-black text-2xl text-white tracking-tight flex items-center gap-2">
                                            AI PERFORMANCE INSIGHT
                                        </h3>
                                        <div className="flex items-center gap-3 mt-1">
                                            <p className="text-xs text-gray-400 font-medium tracking-wide flex items-center gap-2">
                                                <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
                                                {logUser.email}
                                            </p>
                                            <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded-full text-gray-500 font-bold border border-white/5">{logUser.id}</span>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-4">
                                     {/* Period Filter */}
                                     <div className="flex p-1 bg-black/40 rounded-2xl border border-white/10 shadow-inner">
                                        {[1, 7, 30].map(d => (
                                            <button 
                                                key={d}
                                                onClick={() => openLogViewer(logUser, d)}
                                                className={`px-5 py-2 rounded-xl text-[10px] font-black tracking-widest transition-all ${currentPeriod === d ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/40 scale-105' : 'text-gray-500 hover:text-white hover:bg-white/5'}`}
                                            >
                                                {d === 1 ? 'DAILY' : d === 7 ? 'WEEKLY' : 'MONTHLY'}
                                            </button>
                                        ))}
                                    </div>
                                    <button onClick={() => setLogUser(null)} className="w-12 h-12 flex items-center justify-center rounded-2xl bg-white/5 hover:bg-red-500/20 hover:text-red-500 border border-white/5 transition-all text-xl shadow-lg">✕</button>
                                </div>
                            </div>

                            {/* Summary Stats Cards */}
                            {!logsLoading && (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    {(() => {
                                        const total = logs.length;
                                        const totalTokens = logs.reduce((acc, l) => acc + (l.input_tokens || 0) + (l.output_tokens || 0), 0);
                                        const successes = logs.filter(l => l.status === 'success' || l.status === 'done').length;
                                        const rate = total > 0 ? Math.round((successes / total) * 100) : 0;
                                        const avgLat = total > 0 ? (logs.reduce((acc, l) => acc + (l.elapsed_time || 0), 0) / total).toFixed(1) : '0.0';
                                        
                                        const periodLabel = currentPeriod === 1 ? 'DAILY' : currentPeriod === 7 ? 'WEEKLY' : 'MONTHLY';

                                        return (
                                            <>
                                                <div className="bg-gradient-to-br from-blue-600/10 to-transparent border border-blue-500/20 rounded-3xl p-5 flex flex-col justify-between group overflow-hidden relative">
                                                    <div className="absolute -right-4 -bottom-4 text-6xl opacity-5 group-hover:rotate-12 transition-transform">🪙</div>
                                                    <p className="text-[10px] font-black text-blue-400 uppercase tracking-widest mb-1">{periodLabel} TOKEN USAGE</p>
                                                    <div className="flex items-baseline gap-2">
                                                        <span className="text-3xl font-black text-white">{totalTokens.toLocaleString()}</span>
                                                        <span className="text-[10px] text-blue-500 font-bold">TOKENS</span>
                                                    </div>
                                                </div>
                                                <div className="bg-white/5 border border-white/5 rounded-3xl p-5 flex flex-col justify-between">
                                                    <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">TOTAL TASKS</p>
                                                    <div className="flex items-baseline gap-2">
                                                        <span className="text-3xl font-black text-white">{total.toLocaleString()}</span>
                                                        <span className="text-[10px] text-gray-600 font-bold">UNITS</span>
                                                    </div>
                                                </div>
                                                <div className="bg-white/5 border border-white/5 rounded-3xl p-5 flex flex-col justify-between">
                                                    <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">SUCCESS RATE</p>
                                                    <div className="flex items-baseline gap-2">
                                                        <span className={`text-3xl font-black ${rate > 90 ? 'text-green-500' : 'text-orange-500'}`}>{rate}%</span>
                                                        <span className="text-[10px] text-gray-600 font-bold">GLOBAL</span>
                                                    </div>
                                                </div>
                                                <div className="bg-white/5 border border-white/5 rounded-3xl p-5 flex flex-col justify-between">
                                                    <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">AVG LATENCY</p>
                                                    <div className="flex items-baseline gap-2">
                                                        <span className="text-3xl font-black text-blue-400">{avgLat}s</span>
                                                        <span className="text-[10px] text-gray-600 font-bold">PER TASK</span>
                                                    </div>
                                                </div>
                                            </>
                                        );
                                    })()}
                                </div>
                            )}

                            {/* Charts Visualization */}
                            {!logsLoading && logs.length > 0 && (() => {
                                const totalTokens = logs.reduce((acc, l) => acc + (l.input_tokens || 0) + (l.output_tokens || 0), 0);
                                const totalCount = logs.length;

                                // Stage calculation
                                const breakdown: Record<string, any> = {};
                                const stages = ['video', 'image', 'script', 'analysis', 'planning'];
                                stages.forEach(s => breakdown[s] = { tokens: 0, count: 0, buckets: [] });
                                
                                const bc = currentPeriod === 1 ? 24 : currentPeriod === 7 ? 7 : 30;
                                const now = new Date();

                                logs.forEach(l => {
                                    const task = l.task_type || 'unknown';
                                    let mapped = (task === 'scripting' || task === 'script') ? 'script' : task;
                                    if (!stages.includes(mapped)) mapped = 'analysis'; // Fallback for others
                                    
                                    if (!breakdown[mapped].buckets.length) breakdown[mapped].buckets = new Array(bc).fill(0);
                                    
                                    const tk = (l.input_tokens || 0) + (l.output_tokens || 0);
                                    const ld = new Date(l.created_at);
                                    let idx = -1;
                                    
                                    if (currentPeriod === 1) {
                                        idx = ld.getHours();
                                    } else {
                                        const dt = Math.abs(now.getTime() - ld.getTime());
                                        idx = bc - 1 - Math.floor(dt / (1000 * 60 * 60 * 24));
                                    }
                                    
                                    if (idx >= 0 && idx < bc) {
                                        breakdown[mapped].buckets[idx] += tk;
                                    }
                                    
                                    breakdown[mapped].tokens += tk;
                                    breakdown[mapped].count += 1;
                                });

                                const activeStages = stages.filter(s => breakdown[s].count > 0 || ['video', 'image', 'script'].includes(s));

                                // Colors
                                const hexMap: Record<string, string> = { video: '#f97316', image: '#3b82f6', script: '#22c55e', analysis: '#a855f7', planning: '#6366f1' };
                                const bgMap: Record<string, string> = { video: 'bg-orange-500', image: 'bg-blue-500', script: 'bg-green-500', analysis: 'bg-purple-500', planning: 'bg-indigo-500' };

                                let ang = 0;
                                const slices = activeStages.map(s => {
                                    const p = totalTokens > 0 ? (breakdown[s].tokens / totalTokens) * 100 : 0;
                                    const color = hexMap[s] || '#64748b';
                                    const res = `${color} ${ang}% ${ang + p}%`;
                                    ang += p;
                                    return { stage: s, p, color, res };
                                });

                                return (
                                    <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 mt-2">
                                        {/* Activity Bars */}
                                        <div className="xl:col-span-3 grid grid-cols-1 md:grid-cols-3 gap-3">
                                            {['video', 'image', 'script'].map(s => {
                                                const d = breakdown[s];
                                                const maxBk = Math.max(...d.buckets, 1);
                                                return (
                                                    <div key={s} className="bg-white/5 border border-white/5 rounded-3xl p-5 flex flex-col justify-between min-h-[160px] hover:bg-white/[0.08] transition-all group overflow-hidden">
                                                        <div className="flex justify-between items-start">
                                                            <div>
                                                                <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1 group-hover:text-white transition-colors">{s}</p>
                                                                <div className="text-2xl font-black text-white flex items-baseline gap-1">
                                                                    {d.count}
                                                                    <span className="text-[10px] text-gray-600 font-bold">건</span>
                                                                </div>
                                                            </div>
                                                            <div className={`w-8 h-8 rounded-xl ${bgMap[s]} bg-opacity-10 flex items-center justify-center`}>
                                                                <div className={`w-2 h-2 rounded-full ${bgMap[s]} animate-pulse`} />
                                                            </div>
                                                        </div>
                                                        {/* Sparkline */}
                                                        <div className="flex items-end gap-[2px] h-12 w-full mt-4">
                                                            {d.buckets.map((v: number, i: number) => {
                                                                let h = (v / maxBk) * 100;
                                                                if (v === 0 && d.buckets.some((b: number) => b > 0)) h = 10; // Tiny baseline for consistency
                                                                return (
                                                                    <div key={i} className={`flex-1 ${bgMap[s] || 'bg-gray-500'} rounded-t-sm transition-all duration-500`} style={{height: `${Math.max(8, h)}%`, opacity: v > 0 ? 1 : 0.05}} />
                                                                );
                                                            })}
                                                        </div>
                                                        <div className="flex justify-between items-center mt-3 pt-3 border-t border-white/5">
                                                            <div className="text-[10px] font-black text-white leading-none">
                                                                {d.tokens.toLocaleString()} <span className="text-gray-600 ml-0.5">TK</span>
                                                            </div>
                                                            <div className="text-[9px] font-bold text-gray-500 uppercase tracking-tighter">
                                                                {currentPeriod === 1 ? 'Last 24h' : `Last ${currentPeriod}d`}
                                                            </div>
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        {/* Donut Chart */}
                                        <div className="bg-white/5 border border-white/5 rounded-[2.5rem] p-6 flex flex-col items-center justify-center relative shadow-xl overflow-hidden group">
                                            <div className="absolute top-0 right-0 p-3 opacity-20 pointer-events-none">
                                                <div className="w-16 h-16 border-4 border-white/10 rounded-full" />
                                            </div>
                                            <div className="relative w-36 h-36 rounded-full shadow-2xl transition-transform group-hover:scale-105 duration-500" style={{background: totalTokens > 0 ? `conic-gradient(${slices.map(s => s.res).join(', ')})` : '#1e293b'}}>
                                                <div className="absolute inset-6 bg-gray-900 rounded-full flex flex-col items-center justify-center shadow-inner">
                                                    <span className="text-xs font-black text-white">{totalTokens > 1000 ? (totalTokens/1000).toFixed(1) + 'K' : totalTokens}</span>
                                                    <span className="text-[8px] text-gray-500 font-black uppercase mt-0.5 tracking-widest">TK ALL</span>
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-2 gap-x-4 gap-y-2 mt-8 w-full">
                                                {slices.filter(s => s.p > 0).map(s => (
                                                    <div key={s.stage} className="flex items-center gap-2">
                                                        <div className="w-2 h-2 rounded-full shadow-sm" style={{background: s.color}} />
                                                        <span className="text-[9px] font-black text-gray-500 uppercase truncate flex-1 tracking-tight">{s.stage}</span>
                                                        <span className="text-[9px] font-black text-white">{s.p.toFixed(0)}%</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })()}
                        </div>

                        {/* Pagination & Sorting Filter Bar */}
                        <div className="px-8 py-5 border-b border-white/5 bg-white/[0.01] flex flex-wrap justify-between items-center gap-4 flex-shrink-0">
                            <div className="flex items-center gap-3">
                                <div className="flex bg-black/40 p-1 rounded-xl border border-white/10">
                                    <button 
                                        onClick={() => setLogSortOrder('newest')}
                                        className={`px-4 py-1.5 rounded-lg text-[10px] font-black transition-all ${logSortOrder === 'newest' ? 'bg-white/10 text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
                                    >
                                        최신기준
                                    </button>
                                    <button 
                                        onClick={() => setLogSortOrder('oldest')}
                                        className={`px-4 py-1.5 rounded-lg text-[10px] font-black transition-all ${logSortOrder === 'oldest' ? 'bg-white/10 text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
                                    >
                                        과거기준
                                    </button>
                                </div>
                                <select 
                                    value={logPageSize} 
                                    onChange={(e) => { setLogPageSize(Number(e.target.value)); setLogCurrentPage(1); }}
                                    className="bg-black/40 border border-white/10 text-[10px] font-black text-gray-400 px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-white/20"
                                >
                                    <option value="10">10개씩</option>
                                    <option value="20">20개씩</option>
                                    <option value="50">50개씩</option>
                                    <option value="100">100개씩</option>
                                </select>
                            </div>

                            {!logsLoading && logs.length > logPageSize && (
                                <div className="flex items-center gap-2">
                                    <button 
                                        disabled={logCurrentPage === 1}
                                        onClick={() => setLogCurrentPage(p => Math.max(1, p - 1))}
                                        className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5 border border-white/5 text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                                    >
                                        ←
                                    </button>
                                    <span className="text-[10px] font-black text-gray-400 px-3">
                                        PAGE <span className="text-white">{logCurrentPage}</span> / {Math.ceil(logs.length / logPageSize)}
                                    </span>
                                    <button 
                                        disabled={logCurrentPage >= Math.ceil(logs.length / logPageSize)}
                                        onClick={() => setLogCurrentPage(p => p + 1)}
                                        className="w-8 h-8 flex items-center justify-center rounded-lg bg-white/5 border border-white/5 text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                                    >
                                        →
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* Table */}
                        <div className="overflow-y-auto flex-1 p-8 pt-6">
                            <div className="bg-black/20 rounded-[2.5rem] border border-white/5 overflow-hidden shadow-2xl">
                                {logsLoading ? (
                                    <div className="flex flex-col items-center justify-center py-40 gap-4">
                                        <div className="w-12 h-12 border-4 border-blue-600/20 border-t-blue-600 rounded-full animate-spin shadow-lg" />
                                        <div className="text-gray-500 font-black text-[10px] uppercase tracking-[0.3em] animate-pulse">SYNCHRONIZING RECORDS...</div>
                                    </div>
                                ) : logs.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center py-40 gap-3 opacity-20">
                                        <span className="text-6xl grayscale">📡</span>
                                        <div className="text-gray-500 font-black text-xs uppercase tracking-[0.2em] italic">NO DATA PACKETS FOUND</div>
                                    </div>
                                ) : (
                                    <table className="w-full text-left text-xs border-collapse">
                                        <thead>
                                            <tr className="bg-white/[0.04] text-gray-500 font-black uppercase tracking-widest text-[9px] border-b border-white/5">
                                                <th className="px-10 py-6">TIMESTAMP</th>
                                                <th className="px-10 py-6">CATEGORY</th>
                                                <th className="px-10 py-6">INFRASTRUCTURE</th>
                                                <th className="px-10 py-6 text-orange-500">AI 토큰 소모량</th>
                                                <th className="px-10 py-6 text-blue-500">남은 토큰 총량</th>
                                                <th className="px-10 py-6 text-center">STATUS</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/5 bg-white/[0.01]">
                                            {(() => {
                                                const sortedLogs = [...logs].sort((a, b) => {
                                                    const timeA = new Date(a.created_at).getTime();
                                                    const timeB = new Date(b.created_at).getTime();
                                                    return logSortOrder === 'newest' ? timeB - timeA : timeA - timeB;
                                                });
                                                const pagedLogs = sortedLogs.slice((logCurrentPage - 1) * logPageSize, logCurrentPage * logPageSize);

                                                return pagedLogs.map(log => {
                                                    const d = new Date(log.created_at)
                                                    const timeStr = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
                                                    const dateStr = `${d.getFullYear()}. ${String(d.getMonth()+1).padStart(2,'0')}. ${String(d.getDate()).padStart(2,'0')}`
                                                    
                                                    const isSuccess = log.status === 'success' || log.status === 'done';
                                                    const stageColor = log.task_type === 'video' ? 'bg-orange-500' : log.task_type === 'image' ? 'bg-blue-500' : 'bg-green-500';

                                                    return (
                                                        <tr key={log.id} className="hover:bg-white/[0.04] transition-all group border-b border-white/[0.02]">
                                                            <td className="px-10 py-6">
                                                                <div className="font-black text-white text-[12px] group-hover:text-blue-400 transition-colors">{timeStr}</div>
                                                                <div className="text-[10px] text-gray-600 font-bold mt-1 tracking-tight">{dateStr}</div>
                                                            </td>
                                                            <td className="px-10 py-6">
                                                                <div className="flex items-center gap-3">
                                                                    <div className={`w-2.5 h-2.5 rounded-full shadow-lg ${stageColor}`} />
                                                                    <span className="font-black uppercase text-[11px] text-gray-300 tracking-tighter group-hover:text-white transition-colors">
                                                                        {log.task_type}
                                                                    </span>
                                                                </div>
                                                            </td>
                                                            <td className="px-10 py-6">
                                                                <div className="text-[12px] font-black text-gray-200 group-hover:text-white transition-colors">{log.model_id}</div>
                                                                <div className="text-[10px] text-gray-600 font-black uppercase mt-1 tracking-widest">{log.provider}</div>
                                                            </td>
                                                            <td className="px-10 py-6">
                                                                <div className="flex flex-col gap-1.5 items-start">
                                                                    <div className="flex items-center gap-2">
                                                                         <div className={`px-2 py-0.5 rounded border ${log.task_type === 'RECHARGE' ? 'bg-green-500/10 border-green-500/20' : 'bg-blue-500/10 border-blue-500/20'}`}>
                                                                            <span className={`text-[11px] font-black tracking-tight ${log.task_type === 'RECHARGE' ? 'text-green-500' : 'text-blue-400'}`}>
                                                                                {log.task_type === 'RECHARGE' ? '+' : ''}{((log.input_tokens || 0) + (log.output_tokens || 0) + (log.thinking_tokens || 0)).toLocaleString()}
                                                                            </span>
                                                                         </div>
                                                                         {log.thinking_tokens ? (
                                                                             <span className="text-[9px] bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded border border-purple-500/20 font-black">
                                                                                 THINKING: {log.thinking_tokens.toLocaleString()}
                                                                             </span>
                                                                         ) : null}
                                                                         <span className="text-[10px] text-gray-600 font-black tracking-tighter">TOKENS</span>
                                                                    </div>
                                                                    <div className="text-[10px] text-gray-500 line-clamp-1 italic max-w-sm group-hover:text-gray-300 transition-colors" title={log.prompt_summary}>
                                                                        "{log.prompt_summary || 'No prompt info'}"
                                                                    </div>
                                                                    {log.error_msg && (
                                                                        <div className="text-[10px] text-red-400 font-bold bg-red-500/10 border border-red-500/20 rounded px-2 py-1 mt-1 max-w-sm" title={log.error_msg}>
                                                                            ⚠️ {log.error_msg}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </td>
                                                            <td className="px-10 py-6">
                                                                <div className="text-[12px] font-black text-blue-500 tabular-nums">
                                                                    {log.balance_after ? log.balance_after.toLocaleString() : '-'}
                                                                </div>
                                                            </td>
                                                            <td className="px-10 py-6 text-center">
                                                                <div className="flex flex-col items-center gap-2">
                                                                    {isSuccess ? (
                                                                        <span className="bg-green-500/10 text-green-500 px-4 py-1.5 rounded-xl font-black text-[10px] border border-green-500/20 shadow-lg shadow-green-900/10">SUCCESS</span>
                                                                    ) : (
                                                                        <span className="bg-red-500/10 text-red-500 px-4 py-1.5 rounded-xl font-black text-[10px] border border-red-500/20 shadow-lg shadow-red-900/10">FAILURE</span>
                                                                    )}
                                                                    <div className="flex items-center gap-1.5 opacity-60">
                                                                        <span className="w-1 h-1 rounded-full bg-gray-600" />
                                                                        <span className="text-[10px] font-black text-gray-500 tracking-widest">{log.elapsed_time?.toFixed(1)}S</span>
                                                                    </div>
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    )
                                                });
                                            })()}
                                        </tbody>
                                    </table>
                                )}
                            </div>
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

                            {/* PIN 번호 설정 */}
                            <div>
                                <label className="text-[10px] font-black text-blue-400 uppercase tracking-widest mb-1 block">
                                    🔑 간편 로그인 PIN 번호 (4자리 숫자)
                                </label>
                                <input
                                    type="text"
                                    maxLength={4}
                                    value={pinCode}
                                    onChange={e => setPinCode(e.target.value.replace(/[^0-9]/g, ''))}
                                    placeholder="기본값: 1234"
                                    className="w-full bg-black/40 border border-white/10 text-xs px-4 py-2.5 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/50 font-mono text-gray-300 placeholder:text-gray-700"
                                />
                            </div>

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
                    <button
                        onClick={() => setActiveTab('categories')}
                        className={`px-6 py-3 rounded-2xl font-black text-sm transition-all flex items-center gap-2 ${activeTab === 'categories' ? 'bg-indigo-600 text-white shadow-lg' : 'bg-white/5 text-gray-500 hover:bg-white/10'}`}
                    >
                        🎯 AI 주제 자판기 관리
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
                                        <th className="px-6 py-3">{t.emailId}</th>
                                        <th className="px-6 py-3">로그인 PIN</th>
                                        <th className="px-6 py-3">{t.fullName}</th>
                                        <th className="px-6 py-3">{t.nationality}</th>
                                        <th className="px-6 py-3">{t.contact}</th>
                                        <th className="px-6 py-3">{t.joinDate}</th>
                                        <th className="px-6 py-3">{t.lastLogin}</th>
                                        <th className="px-6 py-3 text-center">보유 토큰</th>
                                        <th className="px-6 py-3 text-center">{t.membership}</th>
                                        <th className="px-6 py-3 text-center">{t.manage}</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5 font-medium">
                                    {users.map((user) => (
                                        <tr key={user.id} className="hover:bg-white/5 transition-all h-24 cursor-pointer" onClick={() => openUserPanel(user)}>
                                            <td className="px-6 py-4">
                                                <div className="font-bold text-white text-sm tracking-tight">{user.email?.toLowerCase()}</div>
                                                <div className="text-[9px] text-gray-600 font-mono mt-0.5 opacity-70 tracking-tighter truncate max-w-[150px]">{user.id}</div>
                                                {user.user_metadata?.referrer && (
                                                    <div className="mt-1 flex items-center gap-1">
                                                        <span className="text-[9px] text-yellow-500/70 font-bold uppercase tracking-widest">추천:</span>
                                                        <span className="text-[9px] text-yellow-400 font-bold">{user.user_metadata.referrer}</span>
                                                    </div>
                                                )}
                                            </td>
                                            <td className="px-6 py-4">
                                                <span className="bg-blue-500/10 text-blue-400 border border-blue-500/20 px-2.5 py-1 rounded-lg font-mono font-bold text-xs">
                                                    {user.profile?.pin_code || '1234'}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-gray-300 text-xs font-bold">
                                                {user.user_metadata?.full_name || '-'}
                                            </td>
                                            <td className="px-6 py-4 text-gray-400 text-xs">
                                                {user.user_metadata?.nationality || '-'}
                                            </td>
                                            <td className="px-6 py-4 text-gray-400 text-xs">
                                                {user.user_metadata?.contact || '-'}
                                            </td>
                                            <td className="px-6 py-4 text-gray-400 text-xs">
                                                {formatDate(user.created_at)}
                                            </td>
                                            <td className="px-6 py-4 text-gray-400 text-xs">
                                                {formatDate(user.last_sign_in_at)}
                                            </td>
                                            <td className="px-6 py-4 text-center">
                                                <div className="flex flex-col items-center gap-1 group/token bg-white/[0.03] p-3 rounded-2xl border border-white/5 hover:border-blue-500/30 transition-all">
                                                    <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-0.5">CURRENT BALANCE</div>
                                                    <span className="text-white font-black text-lg tracking-tight">{user.profile?.token_balance?.toLocaleString() || 0}</span>
                                                    <div className="flex gap-1 mt-1">
                                                        <button
                                                            onClick={(e) => { e.stopPropagation(); rechargeTokens(user.id); }}
                                                            className="px-3 py-1 bg-blue-600/20 hover:bg-blue-600 text-blue-400 hover:text-white text-[10px] font-black rounded-lg transition-all border border-blue-600/20 uppercase tracking-tighter"
                                                        >
                                                            ⚡ RECHARGE
                                                        </button>
                                                        <button
                                                            onClick={(e) => openTxViewer(user, e)}
                                                            className="px-3 py-1 bg-gray-700/40 hover:bg-gray-600 text-gray-400 hover:text-white text-[10px] font-black rounded-lg transition-all border border-gray-600/20 uppercase tracking-tighter"
                                                        >
                                                            📋 내역
                                                        </button>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-6 py-4 text-center">
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
                                            <td className="px-6 py-4 text-center">
                                                <div className="flex justify-center gap-2">
                                                    <button
                                                        onClick={(e) => openLogViewer(user, 1, e)}
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
                ) : activeTab === 'categories' ? (
                    <div className="space-y-8 animate-in fade-in duration-300">
                        {/* 1. 카테고리 추가 폼 */}
                        <div className="bg-[#111] rounded-[2.5rem] border border-white/5 p-8 shadow-2xl">
                            <h2 className="font-black text-xl tracking-tight mb-6 flex items-center gap-2">
                                ➕ 새 카테고리 및 직원 매핑 추가
                            </h2>
                            <form onSubmit={handleCreateCategory} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">카테고리명 *</label>
                                    <input 
                                        type="text" 
                                        required
                                        placeholder="예: 세계 미스터리"
                                        value={newCatName}
                                        onChange={e => setNewCatName(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">담당 직원 이메일 *</label>
                                    <select
                                        required
                                        value={newCatEmployee}
                                        onChange={e => setNewCatEmployee(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="">-- 직원을 선택하세요 --</option>
                                        {users.map(user => {
                                            const email = user.email?.toLowerCase();
                                            if (!email) return null;
                                            const name = user.user_metadata?.full_name || '';
                                            return (
                                                <option key={user.id} value={email} className="bg-[#111] text-white">
                                                    {email} {name ? `(${name})` : ''}
                                                </option>
                                            );
                                        })}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">주요 리서치 키워드</label>
                                    <input 
                                        type="text" 
                                        placeholder="쉼표로 구분 (예: 버뮤다 삼각지대, 미해결 사건)"
                                        value={newCatKeywords}
                                        onChange={e => setNewCatKeywords(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">벤치마킹할 유튜브 채널 URL</label>
                                    <input 
                                        type="url" 
                                        placeholder="예: https://www.youtube.com/@BenchmarkChannel"
                                        value={newCatChannel}
                                        onChange={e => setNewCatChannel(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">기본 대본 스타일 *</label>
                                    <select
                                        required
                                        value={newCatScriptStyle}
                                        onChange={e => setNewCatScriptStyle(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="default" className="bg-[#111] text-white">기본 설정 (선명하고 자연스럽게)</option>
                                        <option value="story" className="bg-[#111] text-white">옛날 이야기 (구연동화 톤)</option>
                                        <option value="senior_story" className="bg-[#111] text-white">시니어 이야기 (회상/감성 톤)</option>
                                        <option value="news" className="bg-[#111] text-white">뉴스 (정보전달 톤)</option>
                                        <option value="mystery_thriller" className="bg-[#111] text-white">미스터리 스릴러 (긴장감 톤)</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">전래동요풍 (어린이 구연 톤)</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-black text-gray-400 mb-1.5 block uppercase tracking-wider">기본 이미지 화풍 *</label>
                                    <select
                                        required
                                        value={newCatImageStyle}
                                        onChange={e => setNewCatImageStyle(e.target.value)}
                                        className="w-full px-4 py-3 bg-black/40 border border-white/10 rounded-xl text-white outline-none focus:ring-2 focus:ring-blue-500/50 cursor-pointer"
                                    >
                                        <option value="realistic" className="bg-[#111] text-white">실사 (Photorealistic)</option>
                                        <option value="ghibli" className="bg-[#111] text-white">지브리 감성 일러스트 (Ghibli)</option>
                                        <option value="anime" className="bg-[#111] text-white">일본 애니메이션풍 (Anime)</option>
                                        <option value="cinematic" className="bg-[#111] text-white">영화 스틸컷 느낌 (Cinematic)</option>
                                        <option value="cartoon" className="bg-[#111] text-white">2D 카툰 일러스트 (Cartoon)</option>
                                        <option value="nursery_rhyme" className="bg-[#111] text-white">3D 동화/애니 (Nursery/Pixar)</option>
                                        <option value="역사/동양철/다큐" className="bg-[#111] text-white">전통 동양화/수묵화 (Ink Wash)</option>
                                    </select>
                                </div>
                                <div className="md:col-span-3 mt-4 flex justify-end">
                                    <button 
                                        type="submit"
                                        className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-black rounded-xl transition-all shadow-lg active:scale-95 flex items-center justify-center gap-2"
                                    >
                                        🚀 등록 및 초기 주제 생성
                                    </button>
                                </div>
                            </form>
                        </div>

                        {/* 2. 등록된 카테고리 및 매핑 리스트 */}
                        <div className="bg-[#111] rounded-[2.5rem] border border-white/5 overflow-hidden shadow-2xl p-8">
                            <h2 className="font-black text-xl tracking-tight mb-6">📂 내 카테고리 현황</h2>
                            {categoriesLoading ? (
                                <div className="text-center py-20 text-gray-500 text-sm">카테고리 로딩 중...</div>
                            ) : categories.length === 0 ? (
                                <div className="text-center py-20 text-gray-500 text-sm italic">등록된 카테고리가 없습니다.</div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {categories.map((cat) => {
                                        const pendingTopics = topics.filter(t => t.category_id === cat.id && t.status === 'pending');
                                        const completedTopics = topics.filter(t => t.category_id === cat.id && t.status === 'completed');

                                        return (
                                            <div key={cat.id} className="bg-black/40 border border-white/10 rounded-3xl p-6 relative flex flex-col justify-between hover:border-indigo-500/50 transition-all">
                                                <div>
                                                    <div className="flex justify-between items-start mb-4">
                                                        <h3 className="text-lg font-black text-white">{cat.name}</h3>
                                                        <button 
                                                            onClick={() => handleDeleteCategory(cat.id)}
                                                            className="text-gray-500 hover:text-red-500 text-xs transition-colors"
                                                        >
                                                            삭제
                                                        </button>
                                                    </div>
                                                    <div className="space-y-2 text-xs text-gray-400 mb-6">
                                                        <p>👤 <strong className="text-gray-200">담당 직원:</strong> {cat.assigned_employee_email}</p>
                                                        <p>🔑 <strong className="text-gray-200">키워드:</strong> {cat.keywords || '(없음)'}</p>
                                                        <p className="truncate">📺 <strong className="text-gray-200">채널:</strong> <a href={cat.benchmark_channel_url} target="_blank" rel="noreferrer" className="text-indigo-400 underline">{cat.benchmark_channel_url || '(없음)'}</a></p>
                                                    </div>
                                                    
                                                    {/* 주제 대기열 카운트 */}
                                                    <div className="flex gap-3 text-[11px] font-black tracking-wider uppercase mb-6">
                                                        <span className="px-3 py-1 bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 rounded-lg">대기주제: {pendingTopics.length}개</span>
                                                        <span className="px-3 py-1 bg-green-500/10 text-green-500 border border-green-500/20 rounded-lg">완료주제: {completedTopics.length}개</span>
                                                    </div>
                                                </div>

                                                <button 
                                                    disabled={generatingCatId === cat.id}
                                                    onClick={() => handleTriggerAiTopics(cat.id)}
                                                    className="w-full py-2.5 bg-indigo-600/20 hover:bg-indigo-600 border border-indigo-500/20 hover:border-transparent text-indigo-400 hover:text-white rounded-xl text-xs font-black tracking-wider transition-all disabled:bg-gray-800 disabled:text-gray-500 disabled:cursor-not-allowed uppercase"
                                                >
                                                    {generatingCatId === cat.id ? '🤖 AI 주제 분석 발굴 중...' : '🔮 AI 주제 자판기 생성 (10개)'}
                                                </button>
                                            </div>
                                        )
                                    })}
                                </div>
                            )}
                        </div>

                        {/* 3. 전체 주제 대기열 큐 모니터링 */}
                        <div className="bg-[#111] rounded-[2.5rem] border border-white/5 overflow-hidden shadow-2xl">
                            <div className="p-8 border-b border-white/5 bg-white/5 flex justify-between items-center">
                                <h2 className="font-black text-xl tracking-tight">📋 실시간 전체 주제 대기열 큐 (Topics Queue)</h2>
                                <span className="bg-yellow-500/20 text-yellow-500 text-[11px] px-3 py-1 rounded-full font-black">
                                    총 대기 건수: {topics.filter(t => t.status === 'pending').length}개
                                </span>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left text-sm">
                                    <thead className="bg-black/40 text-gray-500 font-black h-14 uppercase text-[10px] tracking-widest">
                                        <tr>
                                            <th className="px-10 py-3">카테고리</th>
                                            <th className="px-10 py-3">제안 영상 주제</th>
                                            <th className="px-10 py-3">배정된 직원 이메일</th>
                                            <th className="px-10 py-3 text-center">배당 상태</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-white/5 font-medium">
                                        {topics.map((item) => (
                                            <tr key={item.id} className="hover:bg-white/5 transition-all h-16 text-xs">
                                                <td className="px-10 py-3 text-gray-300 font-bold">
                                                    {(item as any).categories?.name || '기본'}
                                                </td>
                                                <td className="px-10 py-3 text-white font-bold max-w-sm truncate">
                                                    <div className="flex items-center gap-2">
                                                        <span className="truncate">{item.topic}</span>
                                                        {item.is_auto_generated && (
                                                            <span className="bg-purple-500/10 text-purple-400 px-1.5 py-0.5 rounded border border-purple-500/20 font-black text-[8px] tracking-tight shrink-0">
                                                                🤖 AUTO
                                                            </span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="px-10 py-3 text-gray-400">
                                                    {item.assigned_employee_email}
                                                </td>
                                                <td className="px-10 py-3 text-center">
                                                    <span className={`px-2.5 py-1 rounded-full text-[10px] font-black border uppercase tracking-tighter ${
                                                        item.status === 'pending' ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' :
                                                        item.status === 'assigned' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20' :
                                                        'bg-green-500/10 text-green-500 border-green-500/20'
                                                    }`}>
                                                        {item.status === 'pending' ? '대기 중' : item.status === 'assigned' ? '제작 진행 중' : '제작 완료'}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                        {topics.length === 0 && (
                                            <tr>
                                                <td colSpan={4} className="px-10 py-20 text-center text-gray-600 font-black uppercase tracking-widest text-xs italic">
                                                    대기열에 등록된 주제가 없습니다. 카테고리를 먼저 생성해주세요.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
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
