
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
                <div className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-4">
                    <div>
                        <h2 className="text-3xl font-bold mb-2 font-outfit tracking-tight">안녕하세요, 크리에이터님! 👋</h2>
                        <p className="text-gray-400">현재 구독 중인 플랜: <span className="text-blue-400 font-extrabold px-2 py-0.5 bg-blue-500/10 rounded-md border border-blue-500/20">Pro Plan</span></p>
                    </div>
                    <div className="bg-white/5 border border-white/10 px-4 py-2 rounded-lg backdrop-blur-sm">
                        <span className="text-xs text-gray-500 block uppercase font-bold tracking-widest">Latest Version</span>
                        <span className="text-sm font-mono text-green-400">v{latestVersion} Stable</span>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {/* License Card */}
                    <div className="bg-gray-800/50 p-8 rounded-3xl border border-gray-700/50 hover:border-blue-500/50 transition-all duration-500 shadow-2xl relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-6 opacity-5 group-hover:opacity-10 transition-opacity">
                            <span className="text-6xl">🔑</span>
                        </div>
                        <h3 className="text-xl font-bold mb-6 flex items-center gap-2">
                            License Key
                        </h3>
                        <div className="bg-black/40 p-5 rounded-2xl font-mono text-yellow-500 mb-6 break-all border border-white/5 shadow-inner leading-relaxed">
                            {user?.id}
                        </div>
                        <button
                            onClick={() => {
                                navigator.clipboard.writeText(user?.id)
                                alert('라이선스 키가 복사되었습니다!')
                            }}
                            className="w-full py-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 rounded-2xl transition-all font-bold shadow-lg shadow-blue-900/20 active:scale-[0.98]"
                        >
                            키 복사하기
                        </button>
                    </div>

                    {/* Download Card */}
                    <div className="bg-gray-800/50 p-8 rounded-3xl border border-gray-700/50 hover:border-green-500/50 transition-all duration-500 shadow-2xl relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-6 opacity-5 group-hover:opacity-10 transition-opacity">
                            <span className="text-6xl">📥</span>
                        </div>
                        <h3 className="text-xl font-bold mb-6 flex items-center gap-2">
                            Download Program
                        </h3>
                        <p className="text-sm text-gray-400 mb-8 leading-relaxed">
                            윈도우용 실행 파일을 다운로드하여<br />
                            유튜브 영상 제작을 시작하세요.
                        </p>
                        <a
                            href="YOUR_GOOGLE_DRIVE_DOWNLOAD_LINK_HERE"
                            className="w-full py-4 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 rounded-2xl transition-all font-bold shadow-lg shadow-green-900/20 active:scale-[0.98] flex items-center justify-center gap-2"
                            target="_blank"
                        >
                            설치 파일 다운로드 (Win)
                        </a>
                    </div>

                    {/* Quick Guide Card */}
                    <div className="bg-gray-800/50 p-8 rounded-3xl border border-gray-700/50 hover:border-purple-500/50 transition-all duration-500 shadow-2xl lg:col-span-1 md:col-span-2">
                        <h3 className="text-xl font-bold mb-6 flex items-center gap-2 text-purple-400">
                            Quick Start Guide
                        </h3>
                        <ul className="space-y-4 text-sm text-gray-300">
                            <li className="flex gap-3">
                                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center text-[10px] font-bold border border-purple-500/30">1</span>
                                <span>좌측의 <b>License Key</b>를 복사합니다.</span>
                            </li>
                            <li className="flex gap-3">
                                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center text-[10px] font-bold border border-purple-500/30">2</span>
                                <span>다운로드한 <b>Launcher.exe</b>를 실행합니다.</span>
                            </li>
                            <li className="flex gap-3">
                                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center text-[10px] font-bold border border-purple-500/30">3</span>
                                <span>로그인 창에 복사한 키를 붙여넣으세요.</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </main>
        </div>
    )
}
