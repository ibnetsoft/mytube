import type { Metadata } from 'next'
import {
    AIR_STUDIO_PRIVACY_LAST_UPDATED,
    AIR_STUDIO_PRIVACY_POLICY_EN,
    AIR_STUDIO_PRIVACY_POLICY_KO,
} from '@/lib/legalContent'

export const metadata: Metadata = {
    title: '개인정보처리방침 | AIR STUDIO',
    description: 'AIR STUDIO 개인정보처리방침 및 Google 사용자 데이터 처리 안내',
    alternates: {
        canonical: '/privacy',
    },
}

const sections = AIR_STUDIO_PRIVACY_POLICY_KO.split('\n\n')
const englishSections = AIR_STUDIO_PRIVACY_POLICY_EN.split('\n\n')

export default function PrivacyPolicyPage() {
    return (
        <main className="min-h-screen bg-[#f7f8fb] text-slate-900">
            <div className="mx-auto w-full max-w-4xl px-5 py-10 sm:px-8 sm:py-14">
                <header className="mb-8 border-b border-slate-200 pb-6">
                    <a href="/" className="mb-5 inline-flex items-center gap-3 text-sm font-bold text-slate-600 hover:text-slate-950">
                        <img src="/img/air_logo.png" alt="AIR STUDIO" className="h-9 w-9 rounded-full" />
                        AIR STUDIO
                    </a>
                    <h1 className="text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">
                        개인정보처리방침
                    </h1>
                    <p className="mt-3 text-sm text-slate-600">
                        최종 업데이트: {AIR_STUDIO_PRIVACY_LAST_UPDATED}
                    </p>
                    <p className="mt-4 text-base leading-7 text-slate-700">
                        이 페이지는 Google OAuth 검수 및 사용자가 직접 열람할 수 있도록 제공되는 AIR STUDIO의 공식 개인정보처리방침입니다.
                    </p>
                </header>

                <article className="space-y-6 rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
                    {sections.map((section, index) => {
                        const [firstLine, ...rest] = section.split('\n')
                        const isTitle = index === 0
                        return (
                            <section key={`ko-${index}`} className={isTitle ? 'border-b border-slate-100 pb-5' : ''}>
                                {isTitle ? (
                                    <h2 className="text-2xl font-black text-slate-950">{firstLine}</h2>
                                ) : (
                                    <h2 className="text-lg font-black text-slate-950">{firstLine}</h2>
                                )}
                                {rest.length > 0 && (
                                    <div className="mt-3 space-y-2 text-sm leading-7 text-slate-700">
                                        {rest.map((line, lineIndex) => (
                                            <p key={`${index}-${lineIndex}`}>{line}</p>
                                        ))}
                                    </div>
                                )}
                            </section>
                        )
                    })}
                </article>

                <article lang="en" className="mt-8 space-y-5 rounded-lg border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
                    {englishSections.map((section, index) => {
                        const [firstLine, ...rest] = section.split('\n')
                        return (
                            <section key={`en-${index}`}>
                                {index === 0 ? (
                                    <h2 className="text-2xl font-black text-slate-950">{firstLine}</h2>
                                ) : (
                                    <p className="text-sm leading-7 text-slate-700">
                                        {[firstLine, ...rest].join(' ')}
                                    </p>
                                )}
                            </section>
                        )
                    })}
                </article>
            </div>
        </main>
    )
}
