'use client'
import { subtitleTtsReadiness } from '@/lib/stdTtsReadiness'
import { stdUiText } from '@/lib/stdUiText'
import type { SupportedLocale } from '@/lib/i18n'
export default function StdTtsReadinessNotice({ readiness, subtitles, busy, voices, onJump, compact = false, locale = 'ko' }: {
    readiness: ReturnType<typeof subtitleTtsReadiness>; subtitles: any[]; busy: boolean;
    voices: ReadonlyMap<string, string>; onJump: (index: number) => void; compact?: boolean; locale?: SupportedLocale;
}) {
    if (!subtitles.length) return null
    const ui = (text: string, values?: Record<string, string | number>) => stdUiText(locale, text, values)
    const location = (index: number) => ui('씬 {scene} · 자막 {subtitle}', {scene: subtitles[index].scene_number,
        subtitle: subtitles.slice(0, index + 1).filter(s => Number(s.scene_number) === Number(subtitles[index].scene_number)).length})
    return <div className={compact
        ? 'mt-2 w-full shrink-0 rounded-lg border border-amber-400/30 bg-amber-500/5 p-2 text-[9px] leading-snug'
        : 'mx-2 mb-2 shrink-0 rounded-lg border border-amber-400/30 bg-amber-500/5 p-3 text-[11px]'
    } role="status" aria-busy={busy}>
        <details open>
            <summary className="cursor-pointer text-gray-300">{ui('성우 미지정 {missing}개 · 내레이션 성우와 겹침 {shared}개', {
                missing: readiness.issues.filter(i => i.reason === 'missing').length,
                shared: readiness.issues.filter(i => i.reason === 'shared').length})}</summary>
            <div className={`${compact ? 'mt-1.5 max-h-56 space-y-1' : 'mt-2 max-h-40 space-y-2'} std-sidebar-notice-scrollbar overflow-y-auto`}>
                {readiness.issues.map(issue => <div key={issue.index} className={`rounded border border-white/10 bg-black/15 ${compact ? 'p-1.5' : 'p-2'}`}>
                    <button type="button" onClick={() => onJump(issue.index)} className="font-bold text-cyan-200 underline">{ui('{location}로 이동 →', {location: location(issue.index)})}</button>
                    {issue.reason === 'shared' && <span className={compact ? 'mt-0.5 block text-amber-200' : 'ml-2 text-amber-200'}>{ui('{voice} 성우가 내레이션에도 사용됩니다. 대사 또는 해당 내레이션 성우를 바꿔 주세요.', {voice: voices.get(issue.voice) || issue.voice})}</span>}
                    <div className="mt-1 truncate text-gray-300" title={subtitles[issue.index].text}>{subtitles[issue.index].text}</div>
                    {issue.reason === 'shared' && <div className="mt-1 flex flex-wrap gap-2 text-gray-400">{ui('겹치는 내레이션:')} {issue.narrationIndexes.map(index => <button key={index} type="button" className="text-cyan-200 underline" onClick={() => onJump(index)}>{location(index)}</button>)}</div>}
                </div>)}
            </div>
        </details>
    </div>
}
