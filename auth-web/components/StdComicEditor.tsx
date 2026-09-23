'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { ComicSettings, COMIC_LAYOUT_LABELS, comicPages, comicSceneTimings, normalizeComicSettings } from '@/lib/stdComic'
import { ComicMedia, drawComicPage } from '@/lib/stdComicCanvas'

type Props = {
    value: unknown; scenes: any[]; subtitles: any[]; audioUrl?: string; disabled?: boolean
    onSave: (settings: ComicSettings) => Promise<void>
    onUpload?: (scene: any, file: File) => Promise<unknown>
}
export default function StdComicEditor({ value, scenes, subtitles, audioUrl, disabled, onSave, onUpload }: Props) {
    const saved = useMemo(() => normalizeComicSettings(value), [value])
    const [draft, setDraft] = useState(saved)
    const [open, setOpen] = useState(false)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')
    const [pageIndex, setPageIndex] = useState(0)
    const [time, setTime] = useState(0)
    const [playing, setPlaying] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [audioDuration, setAudioDuration] = useState(0)
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const mediaRef = useRef<ComicMedia[]>([])
    const audioRef = useRef<HTMLAudioElement>(null)
    const dialogRef = useRef<HTMLDialogElement>(null)
    const [uploading, setUploading] = useState(false)
    const pages = useMemo(() => comicPages(scenes, draft), [scenes, draft])
    const timings = useMemo(() => comicSceneTimings(scenes, subtitles, audioDuration), [scenes, subtitles, audioDuration])
    const page = pages[pageIndex] || []
    const pageTimings = page.map(scene => timings.find(t => t.sceneNumber === Number(scene.scene_number))!)
    const start = pageTimings[0]?.start || 0
    const duration = Math.max(.1, (pageTimings[pageTimings.length - 1]?.end || 5) - start)
    const dirty = JSON.stringify(draft) !== JSON.stringify(saved)
    useEffect(() => { setDraft(saved) }, [saved])
    useEffect(() => { setError('') }, [draft.font_size, draft.layout, draft.panels])
    useEffect(() => { setPageIndex(0); setTime(0); setPlaying(false) }, [draft.layout, draft.mode])
    useEffect(() => {
        if (open) dialogRef.current?.showModal()
        else dialogRef.current?.close()
    }, [open])
    useEffect(() => {
        if (!open) return
        let cancelled = false
        const items: ComicMedia[] = []
        setLoaded(false); setError(''); setPlaying(false); setTime(0)
        const load = async () => {
            const font = new FontFace('ComicBalloon', 'url(/fonts/NanumSquareExtraBold.ttf)')
            await font.load(); document.fonts.add(font)
            for (const scene of page) {
                const video = draft.mode === 'moving_comic' ? scene.video_url : (!scene.image_url && scene.video_url)
                const url = video || scene.image_url
                if (!url) throw new Error(`씬 ${scene.scene_number}에 이미지 또는 영상을 추가해 주세요.`)
                const item = video ? document.createElement('video') : new Image()
                item.crossOrigin = 'anonymous'
                items.push(item)
                await new Promise<void>((resolve, reject) => {
                    const timer = window.setTimeout(() => reject(new Error('미디어 로딩 시간이 초과되었습니다. 다시 열어 주세요.')), 20000)
                    const done = () => { clearTimeout(timer); resolve() }
                    item.onerror = () => { clearTimeout(timer); reject(new Error(`씬 ${scene.scene_number} 미디어를 읽지 못했습니다.`)) }
                    if (item instanceof HTMLVideoElement) { item.muted = true; item.playsInline = true; item.preload = 'auto'; item.onloadeddata = done }
                    else item.onload = done
                    item.src = url
                })
            }
            if (!cancelled) { mediaRef.current = items; setLoaded(true) }
        }
        void load().catch(e => { if (!cancelled) setError(e.message) })
        return () => {
            cancelled = true
            for (const item of items) if (item instanceof HTMLVideoElement) { item.pause(); item.removeAttribute('src'); item.load() }
            mediaRef.current = []
        }
        // Reload only the current page assets, not on every balloon style edit.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, pageIndex, draft.mode, draft.layout, JSON.stringify(page.map(s => [s.scene_number, s.image_url, s.video_url]))])

    useEffect(() => {
        if (!playing) return
        let frame = 0, last = performance.now()
        const tick = (now: number) => {
            const delta = (now - last) / 1000; last = now
            setTime(t => Math.min(duration, t + delta))
            frame = requestAnimationFrame(tick)
        }
        frame = requestAnimationFrame(tick)
        return () => cancelAnimationFrame(frame)
    }, [playing, duration])
    useEffect(() => { if (time >= duration) setPlaying(false) }, [time, duration])
    useEffect(() => {
        const audio = audioRef.current
        if (!audio) return
        if (playing) {
            audio.currentTime = start + time
            void audio.play().catch(() => { setPlaying(false); setError('음성을 재생할 수 없습니다. TTS 파일을 확인해 주세요.') })
        } else audio.pause()
        return () => audio.pause()
        // time is synchronized on play/seek; do not restart audio every frame.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [playing, start, audioUrl])
    useEffect(() => {
        if (!open || !loaded || !canvasRef.current) return
        let cancelled = false
        const source = start + Math.min(time, duration - .0001)
        const draw = () => {
            if (cancelled || !canvasRef.current) return
            try { drawComicPage(canvasRef.current, page, mediaRef.current, draft, pageTimings, source) }
            catch (e: any) { setError(e.message); setPlaying(false) }
        }
        mediaRef.current.forEach((item, i) => {
            if (!(item instanceof HTMLVideoElement)) return
            const timing = pageTimings[i]
            const local = draft.mode === 'comic' ? 0 : Math.max(0, Math.min(source - timing.start, timing.duration, Math.max(0, item.duration - .05)))
            if (Math.abs(item.currentTime - local) > .12 || !playing) {
                item.onseeked = draw
                if (Math.abs(item.currentTime - local) > .01) item.currentTime = local
            }
            if (playing && draft.mode === 'moving_comic' && source >= timing.start && source < timing.end && local < item.duration - .05) void item.play().catch(() => {})
            else item.pause()
        })
        draw()
        return () => { cancelled = true }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, loaded, time, playing, draft, start, duration])

    async function save() {
        setBusy(true); setError(''); setNotice('')
        try { await onSave(draft); setNotice('제작 모드를 저장했습니다.') }
        catch (e: any) { setError(e.message || '저장에 실패했습니다.') }
        finally { setBusy(false) }
    }
    async function exportPage() {
        if (!loaded) return
        setPlaying(false); setError('')
        try {
            const output = document.createElement('canvas')
            drawComicPage(output, page, mediaRef.current, draft, pageTimings, start + duration, true)
            const blob = await new Promise<Blob>((resolve, reject) => output.toBlob(b => b ? resolve(b) : reject(new Error('PNG를 만들지 못했습니다.')), 'image/png'))
            const url = URL.createObjectURL(blob), a = document.createElement('a')
            a.href = url; a.download = `comic-page-${String(pageIndex + 1).padStart(3, '0')}.png`; a.click()
            setTimeout(() => URL.revokeObjectURL(url), 1000)
        } catch (e: any) { setError(`페이지 저장 실패: ${e.message}`) }
    }
    const controls = <>
        <label>제작 모드 <select aria-label="제작 모드" disabled={disabled || busy} value={draft.mode} onChange={e => setDraft({ ...draft, mode: e.target.value as ComicSettings['mode'] })} className="rounded border border-white/20 bg-[#171d28] px-2 py-1">
            <option value="standard">기존 영상</option><option value="comic">만화책 · 이미지</option><option value="moving_comic">무빙툰 · 영상 + 이미지</option>
        </select></label>
        <button type="button" disabled={!dirty || busy || disabled} onClick={() => void save()} className="rounded bg-blue-600 px-3 py-1 disabled:opacity-40">{busy ? '저장 중…' : '모드·배치 저장'}</button>
        {dirty && <span className="text-amber-300">저장 전 변경 있음</span>}
    </>
    return <section className="shrink-0 rounded-lg border border-white/10 bg-[#1b2230] p-3 text-xs text-white" aria-label="만화책 제작">
        <div className="flex flex-wrap items-center gap-3">{controls}
            {draft.mode !== 'standard' && <button type="button" onClick={() => setOpen(true)} className="rounded border border-amber-300/50 px-3 py-1 text-amber-100">페이지 편집·미리보기</button>}
        </div>
        {!open && error && <p role="alert" className="mt-2 text-red-300">{error}</p>}
        {!open && notice && <p role="status" className="mt-2 text-emerald-300">{notice}</p>}
        <dialog ref={dialogRef} onCancel={() => { setOpen(false); setPlaying(false) }} className="fixed inset-0 m-auto max-h-[94vh] w-[min(1100px,96vw)] overflow-y-auto rounded-xl border border-white/20 bg-[#171d28] p-5 text-white backdrop:bg-black/80">
            {open && <>
                <div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-bold">만화책 · 무빙툰 편집</h2><button type="button" onClick={() => { setOpen(false); setPlaying(false) }} aria-label="편집 닫기">닫기 ✕</button></div>
                <div className="mb-4 flex flex-wrap gap-3 text-sm">{controls}</div>
                <p className="mb-3 text-xs text-gray-300">가로 16:9 · 씬 순서대로 컷을 배치합니다. 말풍선 문구와 등장 시간은 기존 자막 편집에서 수정합니다. MP4는 모드를 저장한 뒤 기존 렌더 제출을 이용하세요.</p>
                <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
                    <label>배치 <select aria-label="페이지 배치" value={draft.layout} disabled={disabled} onChange={e => setDraft({ ...draft, layout: e.target.value as ComicSettings['layout'] })} className="bg-[#263044] p-1">
                        {Object.entries(COMIC_LAYOUT_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                    </select></label>
                    <label>넘김 시간 <input aria-label="넘김 시간" type="number" step="0.1" min="0.3" max="1.5" value={draft.turn_duration} disabled={disabled} onChange={e => setDraft(normalizeComicSettings({ ...draft, turn_duration: e.target.value }))} className="w-16 bg-[#263044] p-1" /> 초</label>
                    <label>글자 크기 <input aria-label="말풍선 글자 크기" type="number" min="18" max="44" value={draft.font_size} disabled={disabled} onChange={e => setDraft(normalizeComicSettings({ ...draft, font_size: e.target.value }))} className="w-16 bg-[#263044] p-1" /></label>
                    <label><input type="checkbox" checked={draft.dim_inactive} disabled={disabled} onChange={e => setDraft({ ...draft, dim_inactive: e.target.checked })} /> 현재 컷 강조</label>
                    <label><input type="checkbox" checked={draft.turn_sound} disabled={disabled} onChange={e => setDraft({ ...draft, turn_sound: e.target.checked })} /> 넘김 효과음</label>
                </div>
                {audioUrl && <audio ref={audioRef} src={audioUrl} preload="metadata" onLoadedMetadata={e => setAudioDuration(e.currentTarget.duration)} />}
                <canvas ref={canvasRef} width="1280" height="720" className="aspect-video w-full rounded bg-[#f7f2e8]" aria-label="만화책 페이지 미리보기" />
                {!loaded && <p className="mt-2 text-xs">{error ? '컷을 확인해 주세요.' : '페이지 불러오는 중…'}</p>}
                <div className="my-3 flex flex-wrap items-center gap-3 text-sm">
                    <button type="button" disabled={pageIndex === 0} onClick={() => { setPageIndex(i => i - 1); setPlaying(false) }}>← 이전</button>
                    <span>{pageIndex + 1} / {Math.max(1, pages.length)} 페이지</span>
                    <button type="button" disabled={pageIndex + 1 >= pages.length} onClick={() => { setPageIndex(i => i + 1); setPlaying(false) }}>다음 →</button>
                    <button type="button" disabled={!loaded || !!error} onClick={() => { if (time >= duration) setTime(0); setPlaying(p => !p) }} className="rounded bg-blue-600 px-3 py-1">{playing ? '일시정지' : '이 페이지 재생'}</button>
                    <input aria-label="페이지 재생 위치" type="range" min="0" max={duration} step="0.05" value={time} onChange={e => { setPlaying(false); setTime(Number(e.target.value)) }} className="min-w-24 flex-1" />
                    <span>{time.toFixed(1)} / {duration.toFixed(1)}초</span>
                    <button type="button" disabled={!loaded || !!error} onClick={() => void exportPage()} className="rounded border border-white/30 px-3 py-1">현재 페이지 PNG</button>
                </div>
                <p className="mb-3 text-xs text-gray-400">미리보기는 페이지 안의 재생·말풍선을 확인합니다. 페이지 말림과 넘김 효과음은 최종 MP4에 적용됩니다. PNG에는 모든 말풍선과 현재 영상 프레임이 포함됩니다.</p>
                <div className="grid gap-3 sm:grid-cols-2">{page.map(scene => {
                    const key = String(scene.scene_number), panel = draft.panels[key] || {}
                    return <fieldset key={key} disabled={disabled || busy} className="rounded border border-white/15 p-3 text-xs"><legend>씬 {key}</legend>
                        <div className="flex flex-wrap gap-3">
                            <label>그림 맞춤 <select aria-label={`씬 ${key} 그림 맞춤`} value={panel.fit || 'contain'} onChange={e => setDraft({ ...draft, panels: { ...draft.panels, [key]: { ...panel, fit: e.target.value as 'cover' | 'contain' } } })} className="bg-[#263044] p-1"><option value="contain">전체 보이기</option><option value="cover">꽉 채우기</option></select></label>
                            <label>말풍선 <select aria-label={`씬 ${key} 말풍선 위치`} value={panel.bubble_position || 'bottom'} onChange={e => setDraft({ ...draft, panels: { ...draft.panels, [key]: { ...panel, bubble_position: e.target.value as 'top' | 'bottom' } } })} className="bg-[#263044] p-1"><option value="bottom">아래쪽</option><option value="top">위쪽</option></select></label>
                            {onUpload && <label className="cursor-pointer text-blue-200">이미지·영상 교체<input aria-label={`씬 ${key} 미디어 업로드`} type="file" accept="image/png,image/jpeg,image/webp,video/mp4,video/webm,video/quicktime" disabled={dirty || uploading || saved.mode === 'standard'} className="block max-w-full" onChange={async e => {
                                const file = e.target.files?.[0]; e.target.value = ''; if (!file) return
                                setUploading(true); setError('')
                                try { const ok = await onUpload(scene, file); if (ok === false) throw new Error('업로드하지 못했습니다. 원래 화면의 안내를 확인해 주세요.') }
                                catch (err: any) { setError(err.message) } finally { setUploading(false) }
                            }} /></label>}
                        </div>
                    </fieldset>
                })}</div>
                {dirty && <p className="mt-3 text-xs text-amber-300">미디어 교체 전에 모드·배치를 저장해 주세요.</p>}
                {error && <p role="alert" className="mt-3 text-red-300">{error}</p>}
                {notice && <p role="status" className="mt-3 text-emerald-300">{notice}</p>}
            </>}
        </dialog>
    </section>
}
