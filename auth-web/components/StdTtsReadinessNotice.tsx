'use client'
import { subtitleTtsReadiness } from '@/lib/stdTtsReadiness'
export default function StdTtsReadinessNotice({ readiness, subtitles, busy, voices, onJump, compact = false }: {
    readiness: ReturnType<typeof subtitleTtsReadiness>; subtitles: any[]; busy: boolean;
    voices: ReadonlyMap<string, string>; onJump: (index: number) => void; compact?: boolean;
}) {
    if (!busy && readiness.ready) return null
    const location = (index: number) => `씬 ${subtitles[index].scene_number} · 자막 ${subtitles.slice(0, index + 1).filter(s => Number(s.scene_number) === Number(subtitles[index].scene_number)).length}`
    return <div className={compact
        ? 'mt-2 w-full shrink-0 rounded-lg border border-amber-400/30 bg-amber-500/5 p-2 text-[9px] leading-snug'
        : 'mx-2 mb-2 shrink-0 rounded-lg border border-amber-400/30 bg-amber-500/5 p-3 text-[11px]'
    } role="status">
        <div className="font-bold text-amber-200">{busy ? '저장·TTS 작업 중입니다. 완료되면 버튼이 다시 활성화됩니다.' : !subtitles.length ? '자막을 먼저 준비해 주세요.' : `성우 설정 ${readiness.issues.length}개를 확인하면 저장+TTS 버튼이 활성화됩니다.`}</div>
        {!busy && readiness.issues.length > 0 && <details open>
            <summary className="mt-1 cursor-pointer text-gray-300">성우 미지정 {readiness.issues.filter(i => i.reason === 'missing').length}개 · 내레이션 성우와 겹침 {readiness.issues.filter(i => i.reason === 'shared').length}개</summary>
            <div className={`${compact ? 'mt-1.5 max-h-56 space-y-1' : 'mt-2 max-h-40 space-y-2'} std-sidebar-notice-scrollbar overflow-y-auto`}>
                {readiness.issues.map(issue => <div key={issue.index} className={`rounded border border-white/10 bg-black/15 ${compact ? 'p-1.5' : 'p-2'}`}>
                    <button type="button" onClick={() => onJump(issue.index)} className="font-bold text-cyan-200 underline">{location(issue.index)}로 이동 →</button>
                    <span className={compact ? 'mt-0.5 block text-amber-200' : 'ml-2 text-amber-200'}>{issue.reason === 'missing' ? '대사 성우를 선택해 주세요.' : `${voices.get(issue.voice) || issue.voice} 성우가 내레이션에도 사용됩니다. 대사 또는 해당 내레이션 성우를 바꿔 주세요.`}</span>
                    <div className="mt-1 truncate text-gray-300" title={subtitles[issue.index].text}>{subtitles[issue.index].text}</div>
                    {issue.reason === 'shared' && <div className="mt-1 flex flex-wrap gap-2 text-gray-400">겹치는 내레이션: {issue.narrationIndexes.map(index => <button key={index} type="button" className="text-cyan-200 underline" onClick={() => onJump(index)}>{location(index)}</button>)}</div>}
                </div>)}
            </div>
        </details>}
    </div>
}
