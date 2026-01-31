
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'
import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'

// 관리자 이메일 목록
const ADMIN_EMAILS = ['ejsh0519@naver.com']

export default function AdminDashboardContent() {
    const router = useRouter()
    const { t } = useLanguage()
    const [users, setUsers] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [isAdmin, setIsAdmin] = useState(false)

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
                fetchUsers()
            } else {
                setIsAdmin(false)
                setLoading(false)
            }
        }

        initAuth()
        return () => subscription.unsubscribe()
    }, [])

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
        setLoading(false)
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

                {/* Stats Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-12">
                    <div className="bg-white/5 p-8 rounded-[2rem] border border-white/5 shadow-2xl relative overflow-hidden group hover:bg-white/10 transition-all duration-500">
                        <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-all transform group-hover:scale-110">
                            <span className="text-6xl text-white">👥</span>
                        </div>
                        <h3 className="text-gray-500 text-xs font-black uppercase tracking-widest leading-none">{t.totalUsers}</h3>
                        <p className="text-5xl font-black mt-4 text-white tracking-tighter">{users.length}</p>
                    </div>

                    <div className="bg-white/5 p-8 rounded-[2rem] border border-white/5 shadow-2xl relative overflow-hidden group hover:bg-white/10 transition-all duration-500">
                        <div className="absolute top-0 right-0 p-6 opacity-10 group-hover:opacity-20 transition-all transform group-hover:scale-110">
                            <span className="text-6xl text-white">✨</span>
                        </div>
                        <h3 className="text-gray-500 text-xs font-black uppercase tracking-widest leading-none">{t.newUsers}</h3>
                        <p className="text-5xl font-black mt-4 text-green-400 tracking-tighter">
                            {users.filter(u => new Date(u.created_at) > new Date(new Date().setDate(1))).length}
                        </p>
                    </div>

                    <div className="bg-white/5 p-8 rounded-[2rem] border border-white/5 shadow-2xl relative overflow-hidden group opacity-40 grayscale">
                        <div className="absolute top-0 right-0 p-6 opacity-10">
                            <span className="text-6xl text-white">💎</span>
                        </div>
                        <h3 className="text-gray-500 text-xs font-black uppercase tracking-widest leading-none">Paid Subscribers</h3>
                        <p className="text-5xl font-black mt-4 text-purple-400 tracking-tighter">SOON</p>
                    </div>
                </div>

                {/* User Table */}
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
                                    <th className="px-10 py-3 text-center">{t.status}</th>
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
                                            <span className="px-3 py-1 bg-green-500/10 text-green-500 rounded-full text-[10px] font-black border border-green-500/20 uppercase tracking-tighter">
                                                ACTIVE
                                            </span>
                                        </td>
                                        <td className="px-10 py-4 text-center">
                                            <div className="flex justify-center gap-3">
                                                <button className="text-yellow-500/80 hover:text-yellow-400 hover:bg-yellow-500/10 text-[10px] border border-yellow-500/20 px-3 py-2 rounded-xl transition-all font-black uppercase tracking-tighter">
                                                    {t.edit}
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
            </div>
        </div>
    )
}
