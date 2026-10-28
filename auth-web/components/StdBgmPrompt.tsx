'use client'

import { useState } from 'react'
import type { SupportedLocale } from '@/lib/i18n'
import { stdUiText } from '@/lib/stdUiText'

export default function StdBgmPrompt({ payload, locale = 'ko' }: { payload: any; locale?: SupportedLocale }) {
    const ui = (text: string) => stdUiText(locale, text)
    const candidates = [payload?.structure?.bgm_prompt, payload?.bgm_prompt, payload?.structure?.audio_plan?.bgm_prompt]
    const saved = candidates.find(value => typeof value === 'string' ? value.trim() : typeof value?.prompt_en === 'string' && value.prompt_en.trim())
    const prompt = typeof saved === 'string' ? saved.trim() : String(saved?.prompt_en || '').trim()
    const description = typeof saved?.description_ko === 'string' ? saved.description_ko : ''
    const [result, setResult] = useState({ prompt: '', status: '' })
    const status = result.prompt === prompt ? result.status : ''

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(prompt)
            setResult({ prompt, status: 'copied' })
        } catch {
            setResult({ prompt, status: 'failed' })
        }
    }

    return <section aria-label={ui('배경음 프롬프트')} className="rounded-xl border border-white/10 bg-[#1c222c] p-4">
        <div className="flex flex-wrap items-start gap-3">
            <details className="min-w-0 flex-1">
                <summary className="cursor-pointer text-sm font-bold text-white">{ui('배경음 프롬프트')}</summary>
                {prompt ? <div className="mt-3 space-y-2">
                    {description && <p className="text-xs text-gray-400">{description}</p>}
                    <textarea aria-label={ui('배경음 생성 프롬프트')} readOnly value={prompt} rows={5}
                        className="w-full rounded-lg border border-white/10 bg-black/20 p-3 text-xs leading-relaxed text-gray-200" />
                </div> : <p className="mt-3 text-xs text-gray-400">{ui('저장된 배경음 프롬프트가 없습니다.')}</p>}
            </details>
            <button type="button" disabled={!prompt} onClick={copy}
                className="shrink-0 rounded-lg bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-40">
                {ui(status === 'copied' ? '복사 완료' : '프롬프트 복사')}
            </button>
        </div>
        <p role="status" className={status ? 'mt-2 text-xs text-gray-400' : 'sr-only'}>
            {status === 'copied' ? ui('배경음 프롬프트를 복사했습니다.') : status === 'failed' ? ui('복사하지 못했습니다. 프롬프트를 펼쳐 직접 복사해 주세요.') : ''}
        </p>
    </section>
}
