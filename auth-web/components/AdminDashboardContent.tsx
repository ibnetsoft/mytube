
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'

// 관리자 이메일 목록
const ADMIN_EMAILS = ['ejsh0519@naver.com']

export default function AdminDashboardContent() {
    const router = useRouter()
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

    if (loading) return <div className="text-white p-10 text-center bg-gray-900 min-h-screen">데이터를 불러오는 중...</div>

    if (!isAdmin) {
        return (
            <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center justify-center p-4">
                <h1 className="text-2xl font-bold mb-4 text-red-500">🛡️ 관리자 권한이 없습니다.</h1>
                <p className="text-gray-400 mb-8 text-center">
                    현재 세션이 없거나 관리자 계정이 아닙니다.<br />
                    로그인 페이지에서 다시 로그인해 주세요.
                </p>
                <button
                    onClick={() => router.push('/')}
                    className="px-6 py-3 bg-red-600 hover:bg-red-700 rounded-lg font-bold transition shadow-lg"
                >
                    로그인 하러 가기
                </button>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-gray-900 text-white p-8 font-sans">
            <div className="max-w-6xl mx-auto">
                <div className="flex justify-between items-center mb-10">
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent flex items-center gap-2">
                        🛡️ 관리자 대시보드
                    </h1>
                    <button onClick={() => router.push('/dashboard')} className="text-sm text-gray-400 hover:text-white flex items-center gap-1 transition-colors">
                        ← 대시보드로 돌아가기
                    </button>
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
                    <div className="bg-gray-800 p-8 rounded-2xl border border-gray-700 shadow-xl relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <span className="text-4xl text-white">👥</span>
                        </div>
                        <h3 className="text-gray-400 text-sm font-medium">총 사용자</h3>
                        <p className="text-4xl font-black mt-2 text-white">{users.length} 명</p>
                    </div>
                    <div className="bg-gray-800 p-8 rounded-2xl border border-gray-700 shadow-xl relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <span className="text-4xl text-white">✨</span>
                        </div>
                        <h3 className="text-gray-400 text-sm font-medium">이번 달 가입</h3>
                        <p className="text-4xl font-black mt-2 text-green-400">
                            {users.filter(u => new Date(u.created_at) > new Date(new Date().setDate(1))).length} 명
                        </p>
                    </div>
                    <div className="bg-gray-800 p-8 rounded-2xl border border-gray-700 shadow-xl relative overflow-hidden group opacity-60">
                        <div className="absolute top-0 right-0 p-4 opacity-10">
                            <span className="text-4xl text-white">💎</span>
                        </div>
                        <h3 className="text-gray-400 text-sm font-medium">유료 구독자</h3>
                        <p className="text-4xl font-black mt-2 text-purple-400">준비중</p>
                    </div>
                </div>

                {/* User Table */}
                <div className="bg-gray-800 rounded-2xl border border-gray-700 overflow-hidden shadow-2xl">
                    <div className="p-6 border-b border-gray-700 bg-gray-800/50 flex justify-between items-center">
                        <h2 className="font-bold text-xl">회원 목록 관리</h2>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                placeholder="이메일 검색..."
                                className="bg-gray-900 border border-gray-700 text-xs px-3 py-1.5 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                        </div>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-gray-900 text-gray-400 font-semibold h-14">
                                <tr>
                                    <th className="px-8 py-3">이메일 / ID</th>
                                    <th className="px-8 py-3">가입일</th>
                                    <th className="px-8 py-3">마지막 로그인</th>
                                    <th className="px-8 py-3 text-center">상태</th>
                                    <th className="px-8 py-3 text-center">관리</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-750">
                                {users.map((user) => (
                                    <tr key={user.id} className="hover:bg-gray-750/50 transition-colors h-20">
                                        <td className="px-8 py-4">
                                            <div className="font-bold text-white text-base">{user.email}</div>
                                            <div className="text-[10px] text-gray-500 font-mono mt-1 opacity-50 tracking-tighter">{user.id}</div>
                                        </td>
                                        <td className="px-8 py-4 text-gray-300">
                                            {formatDate(user.created_at)}
                                        </td>
                                        <td className="px-8 py-4 text-gray-300">
                                            {formatDate(user.last_sign_in_at)}
                                        </td>
                                        <td className="px-8 py-4 text-center">
                                            <span className="px-3 py-1 bg-green-500/10 text-green-400 rounded-full text-[10px] font-black border border-green-500/20">
                                                ACTIVE
                                            </span>
                                        </td>
                                        <td className="px-8 py-4 text-center">
                                            <div className="flex justify-center gap-2">
                                                <button className="text-yellow-400 hover:text-white hover:bg-yellow-600 text-[10px] border border-yellow-900/50 bg-yellow-900/10 px-3 py-1.5 rounded-lg transition-all font-bold">
                                                    수정
                                                </button>
                                                <button className="text-red-400 hover:text-white hover:bg-red-600 text-[10px] border border-red-900/50 bg-red-900/10 px-3 py-1.5 rounded-lg transition-all font-bold">
                                                    차단
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                                {users.length === 0 && (
                                    <tr>
                                        <td colSpan={5} className="px-8 py-24 text-center text-gray-500">
                                            조회된 사용자 데이터가 없습니다.
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
