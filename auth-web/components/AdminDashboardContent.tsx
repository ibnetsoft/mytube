
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'

// 관리자 이메일 목록
const ADMIN_EMAILS = ['ejsh0519@naver.com']

type Tab = 'users' | 'queue'

export default function AdminDashboardContent() {
    const router = useRouter()
    const { t } = useLanguage()
    const [users, setUsers] = useState<any[]>([])
    const [requests, setRequests] = useState<any[]>([])
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [isAdmin, setIsAdmin] = useState(false)
    const [activeTab, setActiveTab] = useState<Tab>('users')

    useEffect(() => {
        const initAuth = async () => {
            const { data: { session } } = await supabase.auth.getSession()
            handleAuth(session)
        }

        const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
            handleAuth(session)
        })

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
                                        <tr key={user.id} className="hover:bg-white/5 transition-all h-24">
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
                                                <div className="flex justify-center gap-3">
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
