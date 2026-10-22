'use client'
import { subtitleTtsReadiness } from '@/lib/stdTtsReadiness'
import { stdUiText } from '@/lib/stdUiText'
import type { SupportedLocale } from '@/lib/i18n'
export default function StdTtsReadinessNotice({ readiness, subtitles, busy, voices, onJump, missingSpeakerIndexes = [], compact = false, locale = 'ko' }: {
    readiness: ReturnType<typeof subtitleTtsReadiness>; subtitles: any[]; busy: boolean;
    voices: ReadonlyMap<string, string>; onJump: (index: number) => void; missingSpeakerIndexes?: number[]; compact?: boolean; locale?: SupportedLocale;
}) {
    if (!subtitles.length) return null
    const ui = (text: string, values?: Record<string, string | number>) => stdUiText(locale, text, values)
    const location = (index: number) => ui('씬 {scene} · 자막 {subtitle}', {scene: subtitles[index].scene_number,
        subtitle: subtitles.slice(0, index + 1).filter(s => Number(s.scene_number) === Number(subtitles[index].scene_number)).length})
    const sharedDescription = (voice: string, indexes: number[]) => {
        const locations = indexes.map(location).join(', ')
        const name = voices.get(voice) || voice
        return locale === 'en' ? `${name} is assigned to this dialogue and narration at ${locations}. Check the voice assigned to those narration lines or this dialogue.`
            : locale === 'vi' ? `${name} được chọn cho câu thoại này và lời dẫn tại ${locations}. Hãy kiểm tra giọng của các câu lời dẫn đó hoặc câu thoại này.`
            : locale === 'th' ? `${name} ถูกกำหนดให้บทพูดนี้และคำบรรยายที่ ${locations} โปรดตรวจสอบเสียงของคำบรรยายเหล่านั้นหรือบทพูดนี้`
            : `이 대사와 나레이션으로 지정된 ${locations}에 ${name} 성우가 함께 지정되어 있습니다. 해당 나레이션 또는 대사 성우를 확인해 주세요.`
    }
    return <div className={compact
        ? 'mt-2 w-full shrink-0 rounded-lg border border-amber-400/30 bg-amber-500/5 p-2 text-[9px] leading-snug'
        : 'mx-2 mb-2 shrink-0 rounded-lg border border-amber-400/30 bg-amber-500/5 p-3 text-[11px]'
    } role="status" aria-busy={busy}>
        {missingSpeakerIndexes.length > 0 && <div className="mb-2 border-b border-amber-400/20 pb-2">
            <p className="font-bold text-amber-200">{ui('화자 미지정 대사 {count}개', { count: missingSpeakerIndexes.length })}</p>
            <div className="mt-1.5 max-h-56 space-y-1 overflow-y-auto std-sidebar-notice-scrollbar">
                {missingSpeakerIndexes.map(index => <button key={index} type="button" onClick={() => onJump(index)}
                    className="block w-full rounded border border-amber-400/25 bg-black/15 p-2 text-left hover:bg-amber-400/10 focus-visible:outline focus-visible:outline-amber-300">
                    <span className="block font-bold text-cyan-200 underline">{ui('{location}로 이동 →', { location: location(index) })}</span>
                    <span className="mt-1 block truncate text-gray-300" title={subtitles[index].text}>{subtitles[index].text}</span>
                </button>)}
            </div>
        </div>}
        <details open>
            <summary className="cursor-pointer text-gray-300">{ui('성우 미지정 대사 {missing}개 · 내레이션과 같은 성우를 쓰는 대사 {shared}개', {
                missing: readiness.issues.filter(i => i.reason === 'missing').length,
                shared: readiness.issues.filter(i => i.reason === 'shared').length})}</summary>
            <div className={`${compact ? 'mt-1.5 max-h-56 space-y-1' : 'mt-2 max-h-40 space-y-2'} std-sidebar-notice-scrollbar overflow-y-auto`}>
                {readiness.issues.map(issue => <div key={issue.index} className={`rounded border border-white/10 bg-black/15 ${compact ? 'p-1.5' : 'p-2'}`}>
                    <button type="button" onClick={() => onJump(issue.index)} className="font-bold text-cyan-200 underline">{ui('{location}로 이동 →', {location: location(issue.index)})}</button>
                    {issue.reason === 'shared' && <span className={compact ? 'mt-0.5 block text-amber-200' : 'ml-2 text-amber-200'}>{sharedDescription(issue.voice, issue.narrationIndexes)}</span>}
                    <div className="mt-1 truncate text-gray-300" title={subtitles[issue.index].text}>{subtitles[issue.index].text}</div>
                    {issue.reason === 'shared' && <details className="mt-1 text-gray-400">
                        <summary className="cursor-pointer">{ui('같은 성우를 쓰는 내레이션 위치 {count}개 보기', {count: issue.narrationIndexes.length})}</summary>
                        <div className="mt-1 flex flex-wrap gap-2">{issue.narrationIndexes.map(index => <button key={index} type="button" className="text-cyan-200 underline" onClick={() => onJump(index)}>{location(index)}</button>)}</div>
                    </details>}
                </div>)}
            </div>
        </details>
    </div>
}
