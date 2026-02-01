
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabaseClient'
import { useRouter } from 'next/navigation'

import { useLanguage } from '@/lib/LanguageContext'
import LanguageSelector from './LanguageSelector'

export default function DashboardContent() {
    const router = useRouter()
    const { t } = useLanguage()
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

    if (loading) return <div className="min-h-screen bg-gray-900 text-white flex items-center justify-center font-bold tracking-widest animate-pulse">{t.loading}</div>

    return (
        <div className="min-h-screen bg-[#050505] text-white font-sans selection:bg-blue-500/30">
            {/* Top Navigation */}
            <nav className="sticky top-0 z-50 border-b border-white/5 bg-black/60 backdrop-blur-xl px-6 py-4">
                <div className="max-w-7xl mx-auto flex justify-between items-center">
                    <div className="flex items-center gap-8">
                        <h1 className="text-xl font-black bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent italic tracking-tighter">
                            PICADIRI STUDIO
                        </h1>
                    </div>

                    <div className="flex gap-6 items-center">
                        <LanguageSelector />
                        <div className="h-4 w-[1px] bg-white/10 hidden sm:block" />
                        <div className="hidden md:flex flex-col items-end">
                            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-tighter leading-none mb-1">Authenticated as</span>
                            <span className="text-xs font-medium text-blue-400 leading-none">{user?.email}</span>
                        </div>
                        {user?.email === 'ejsh0519@naver.com' && (
                            <button onClick={() => router.push('/admin')} className="px-4 py-2 text-xs bg-red-500/10 hover:bg-red-500/20 text-red-500 border border-red-500/20 rounded-xl transition-all font-bold">
                                {t.adminPanel}
                            </button>
                        )}
                        <button onClick={handleSignOut} className="px-4 py-2 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl transition-all font-bold text-gray-300">
                            {t.logout}
                        </button>
                    </div>
                </div>
            </nav>

            <main className="max-w-7xl mx-auto p-8">
                {/* Header Section */}
                <div className="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-6 pt-4">
                    <div className="space-y-2">
                        <h2 className="text-4xl font-extrabold tracking-tight text-white/90">
                            {t.helloCreator}
                        </h2>
                        <div className="flex items-center gap-2">
                            <p className="text-gray-500 font-medium">{t.currentPlan}:</p>
                            <span className="text-sm font-black text-blue-400 px-3 py-1 bg-blue-500/10 rounded-full border border-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.1)]">Pro Plan</span>
                        </div>
                    </div>
                    <div className="bg-white/5 border border-white/10 p-5 rounded-3xl backdrop-blur-md shadow-2xl flex items-center gap-4 group hover:bg-white/10 transition-all cursor-default">
                        <div className="w-10 h-10 rounded-2xl bg-green-500/20 flex items-center justify-center text-green-400 group-hover:scale-110 transition-transform">
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                        </div>
                        <div>
                            <span className="text-[10px] text-gray-500 block uppercase font-black tracking-widest">{t.version}</span>
                            <span className="text-sm font-mono font-bold text-green-400">v{latestVersion} Stable</span>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {/* License Card */}
                    <div className="bg-[#111] p-10 rounded-[2.5rem] border border-white/5 hover:border-blue-500/30 transition-all duration-700 shadow-2xl relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-20 transition-all duration-700 transform group-hover:scale-125 group-hover:rotate-12">
                            <span className="text-8xl">🔑</span>
                        </div>
                        <h3 className="text-xl font-black mb-8 flex items-center gap-3 text-white/90">
                            {t.licenseKey}
                        </h3>
                        <div className="bg-black/60 p-6 rounded-3xl font-mono text-yellow-500 mb-8 break-all border border-white/5 shadow-inner leading-relaxed group-hover:text-yellow-400 transition-colors">
                            {user?.id}
                        </div>
                        <button
                            onClick={() => {
                                navigator.clipboard.writeText(user?.id)
                                alert(t.keyCopied)
                            }}
                            className="w-full py-5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 rounded-[1.5rem] transition-all font-black text-sm uppercase tracking-widest shadow-xl shadow-blue-900/20 active:scale-[0.98]"
                        >
                            {t.copyKey}
                        </button>
                    </div>

                    {/* Download Card */}
                    <div className="bg-[#111] p-10 rounded-[2.5rem] border border-white/5 hover:border-green-500/30 transition-all duration-700 shadow-2xl relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-20 transition-all duration-700 transform group-hover:scale-125 group-hover:rotate-12">
                            <span className="text-8xl">📥</span>
                        </div>
                        <h3 className="text-xl font-black mb-8 flex items-center gap-3 text-white/90">
                            {t.downloadTitle}
                        </h3>
                        <p className="text-sm text-gray-500 mb-10 leading-relaxed font-medium">
                            {t.downloadDesc}
                        </p>
                        <a
                            href={user?.app_metadata?.membership === 'independent'
                                ? "https://drive.google.com/file/d/pro_link_placeholder"
                                : "https://drive.google.com/file/d/lite_link_placeholder"}
                            className="w-full py-5 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 rounded-[1.5rem] transition-all font-black text-sm uppercase tracking-widest shadow-xl shadow-green-900/20 active:scale-[0.98] flex items-center justify-center gap-3 text-center"
                            target="_blank"
                        >
                            {user?.app_metadata?.membership === 'independent' ? t.downloadPro : t.downloadLite}
                        </a>
                    </div>

                    {/* Quick Guide Card */}
                    <div className="bg-[#111] p-10 rounded-[2.5rem] border border-white/5 hover:border-purple-500/30 transition-all duration-700 shadow-2xl lg:col-span-1 md:col-span-2 relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:opacity-20 transition-all duration-700 transform group-hover:scale-125 group-hover:rotate-12">
                            <span className="text-8xl">🚀</span>
                        </div>
                        <h3 className="text-xl font-black mb-10 flex items-center gap-3 text-purple-400 uppercase tracking-tighter">
                            {t.guideTitle}
                        </h3>
                        <ul className="space-y-6 text-sm text-gray-400 font-medium">
                            <li className="flex gap-4 group/item">
                                <span className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-500/10 text-purple-400 flex items-center justify-center text-xs font-black border border-purple-500/20 group-hover/item:scale-110 transition-transform">1</span>
                                <span className="pt-1">{t.guide1}</span>
                            </li>
                            <li className="flex gap-4 group/item">
                                <span className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-500/10 text-purple-400 flex items-center justify-center text-xs font-black border border-purple-500/20 group-hover/item:scale-110 transition-transform">2</span>
                                <span className="pt-1">{t.guide2}</span>
                            </li>
                            <li className="flex gap-4 group/item">
                                <span className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-500/10 text-purple-400 flex items-center justify-center text-xs font-black border border-purple-500/20 group-hover/item:scale-110 transition-transform">3</span>
                                <span className="pt-1">{t.guide3}</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </main>
        </div>
    )
}
