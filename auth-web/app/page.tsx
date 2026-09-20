
'use client'

import dynamic from 'next/dynamic'

// AuthForm도 클라이언트에서만 렌더링하도록 설정
const AuthForm = dynamic(() => import('../components/AuthForm'), { ssr: false })

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-8 sm:p-8 md:p-16 lg:p-24 bg-gradient-to-br from-indigo-950 via-purple-950 to-black overflow-x-hidden">
      <div className="z-10 w-full max-w-5xl flex flex-col items-center justify-center">
        <div className="mb-4 flex items-center justify-center">
          <img src="/img/air_logo.png" alt="AIR Studio" className="w-20 h-20 sm:w-24 sm:h-24 rounded-full shadow-2xl shadow-blue-500/30 ring-2 ring-white/15" />
        </div>
        <h1 className="text-3xl sm:text-4xl md:text-6xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-pink-500 via-purple-400 to-violet-500 mb-6 sm:mb-8 text-center tracking-tight">
          에어 스튜디오
        </h1>

        <AuthForm />
        <div className="mt-6 flex items-center justify-center gap-3 text-center text-xs font-semibold text-white/60">
          <a href="/terms" className="underline underline-offset-4 transition hover:text-white">
            서비스 이용약관
          </a>
          <span aria-hidden="true">·</span>
          <a href="/privacy" className="underline underline-offset-4 transition hover:text-white">
            개인정보처리방침
          </a>
        </div>
      </div>
    </main>
  )
}
