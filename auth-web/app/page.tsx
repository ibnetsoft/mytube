
'use client'

import dynamic from 'next/dynamic'

// AuthForm도 클라이언트에서만 렌더링하도록 설정
const AuthForm = dynamic(() => import('../components/AuthForm'), { ssr: false })

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24 bg-gradient-to-br from-indigo-900 via-purple-900 to-black">
      <div className="z-10 w-full max-w-5xl items-center justify-between font-mono text-sm lg:flex flex-col">
        <h1 className="text-4xl md:text-6xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-pink-500 to-violet-500 mb-8">
          에어 스튜디오
        </h1>

        <AuthForm />
      </div>
    </main>
  )
}
