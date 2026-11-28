import { useEffect, useRef } from 'react'
import { Play, X } from 'lucide-react'
import type { FinalSceneEffect, FinalScenePlayback } from '@/lib/stdFinalSceneDelivery'

function timeLabel(ms: number) {
    const seconds = ms / 1000
    return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(2).padStart(5, '0')}`
}

export function StdFinalSceneEffects({ scene, onPlay }: {
    scene: FinalSceneEffect
    onPlay: (range: FinalScenePlayback) => void
}) {
    const transition = scene.outgoing
    const playStyle = 'inline-flex min-h-7 items-center gap-1 rounded border border-cyan-400/30 px-2 text-cyan-200 hover:bg-cyan-500/15'
    return (
        <section aria-label={`씬 ${scene.number} 최종 적용 효과`} onClick={event => event.stopPropagation()}
            className="mb-2 mt-1 min-w-0 rounded-lg border border-cyan-500/25 bg-cyan-950/30 p-2 text-xs text-slate-200">
            <div className="flex flex-wrap items-center gap-2">
                <button type="button" className={playStyle} aria-label={`씬 ${scene.number} 최종본 재생`}
                    onClick={() => onPlay({ label: `씬 ${scene.number} · ${scene.title}`, start_ms: scene.start_ms, end_ms: scene.end_ms })}>
                    <Play size={12} aria-hidden="true" /> 씬 재생
                </button>
                <span className="tabular-nums text-slate-300">{timeLabel(scene.start_ms)}–{timeLabel(scene.end_ms)}</span>
                {transition && <button type="button" className={playStyle}
                    aria-label={`씬 ${scene.number}에서 ${transition.to}로 전환 재생`}
                    onClick={() => onPlay({ label: `${scene.number}→${transition.to} · ${transition.effect}`, start_ms: transition.start_ms, end_ms: transition.end_ms })}>
                    {scene.number}→{transition.to} 전환 재생
                </button>}
            </div>
            <p className="mt-2 break-words text-cyan-100">{scene.effects.length ? scene.effects.join(' · ') : '별도 효과 없음'}</p>
            {transition && <p className="mt-1 break-words text-slate-300">다음 컷 · {transition.effect}</p>}
            <details className="mt-1.5">
                <summary className="cursor-pointer font-semibold text-cyan-200">AE 작업 지침</summary>
                <ul className="ml-4 mt-1 list-disc space-y-1 break-words leading-relaxed">
                    {scene.ae_directions.map((direction, index) => <li key={index}>{direction}</li>)}
                    {transition && <li>{transition.ae_direction}</li>}
                </ul>
                {scene.notes.map((note, index) => <p key={index} className="mt-1 break-words text-amber-200">{note}</p>)}
            </details>
        </section>
    )
}

export function StdFinalScenePlayer({ range, version, src, onClose }: {
    range: FinalScenePlayback
    version: number
    src: string
    onClose: () => void
}) {
    const dialog = useRef<HTMLDialogElement>(null)
    const video = useRef<HTMLVideoElement>(null)
    const start = range.start_ms / 1000
    const end = range.end_ms / 1000
    useEffect(() => { dialog.current?.showModal() }, [])
    return (
        <dialog ref={dialog} onClose={onClose} aria-label={`최종본 v${version} ${range.label}`}
            className="m-auto max-h-[90dvh] w-[min(94vw,900px)] overflow-auto rounded-xl border border-white/15 bg-[#181d26] text-white backdrop:bg-black/75">
            <div className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                    <h3 className="text-sm font-semibold">최종본 v{version} · {range.label}</h3>
                    <p className="mt-1 text-xs tabular-nums text-slate-300">{timeLabel(range.start_ms)}–{timeLabel(range.end_ms)}</p>
                </div>
                <button type="button" aria-label="최종본 재생 닫기" className="rounded-md p-2 hover:bg-white/10" onClick={() => dialog.current?.close()}><X size={18} /></button>
            </div>
            <video ref={video} src={`${src}#t=${start.toFixed(3)},${end.toFixed(3)}`} autoPlay playsInline controls
                aria-label={range.label} className="aspect-video w-full bg-black"
                onLoadedMetadata={event => { if (Math.abs(event.currentTarget.currentTime - start) > .08) event.currentTarget.currentTime = start }}
                onPlay={event => { const media = event.currentTarget; if (media.currentTime < start - .08 || media.currentTime >= end) media.currentTime = start }}
                onTimeUpdate={event => { if (event.currentTarget.currentTime >= end) event.currentTarget.pause() }} />
            <div className="flex justify-end px-4 py-2"><button type="button" className="rounded border border-white/15 px-3 py-1.5 text-xs text-cyan-200"
                onClick={() => { const media = video.current; if (media) { media.currentTime = start; void media.play().catch(() => {}) } }}>구간 다시 재생</button></div>
        </dialog>
    )
}
