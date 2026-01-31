
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'

export default function DashboardContent() {
    const router = useRouter()
    const [user, setUser] = useState<any>(null)
    const [loading, setLoading] = useState(true)

    const latestVersion = "2.0.1"

    useEffect(() => {
        const getUser = async () => {
            const { data: { session } } = await supabase.auth.getSession()
            if (!session) {
                router.push('/')
            } else {
                setUser(session.user)
            }
            setLoading(false)
        }
        getUser()
    }, [router])

    const handleSignOut = async () => {
        await supabase.auth.signOut()
        router.push('/')
    }

    if (loading) return <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center">Loading...</div>

    return (
        <div className="min-h-screen bg-gray-900 text-white font-sans">
            <nav className="border-b border-gray-800 bg-gray-950 p-4">
                <div className="max-w-7xl mx-auto flex justify-between items-center">
                    <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                        MyTube Studio Dashboard
                    </h1>
                    <div className="flex gap-4 items-center">
                        <span className="text-sm text-gray-400">{user?.email}</span>
                        {user?.email === 'ejsh0519@naver.com' && (
                            <button onClick={() => router.push('/admin')} className="px-3 py-1 text-sm bg-red-600 hover:bg-red-700 rounded transition font-bold">
                                🛡️ 관리자 페이지
                            </button>
                        )}
                        <button onClick={handleSignOut} className="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded transition">
                            로그아웃
                        </button>
                    </div>
                </div>
            </nav>

            <main className="max-w-7xl mx-auto p-8">
                <div className="mb-10">
                    <h2 className="text-3xl font-bold mb-2">안녕하세요, 크리에이터님! 👋</h2>
                    <p className="text-gray-400">현재 구독 중인 플랜: <span className="text-blue-400 font-bold">Pro Plan</span></p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="bg-gray-800 p-6 rounded-xl border border-gray-700 hover:border-blue-500 transition shadow-lg text-center">
                        <h3 className="text-xl font-semibold mb-4">🔑 내 라이선스 키</h3>
                        <div className="bg-black/50 p-3 rounded font-mono text-yellow-400 mb-4 break-all">
                            {user?.id}
                        </div>
                        <button onClick={() => navigator.clipboard.writeText(user?.id)} className="w-full py-2 bg-blue-600 hover:bg-blue-700 rounded transition font-medium">
                            ID 복사하기
                        </button>
                    </div>
                </div>
            </main>
        </div>
    )
}
