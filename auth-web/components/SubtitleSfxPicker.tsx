'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export default function SubtitleSfxPicker({ assets, value, projectId, headers, disabled, onChange, onOpen }: {
    assets: any[]; value: string; projectId: string; headers: Record<string, string>; disabled?: boolean;
    onChange: (id: string) => void; onOpen: () => void;
}) {
    const [open, setOpen] = useState(false)
    const [search, setSearch] = useState('')
    const [draft, setDraft] = useState(value)
    const [busy, setBusy] = useState('')
    const [sample, setSample] = useState('')
    const [error, setError] = useState('')
    const dialog = useRef<HTMLDivElement>(null)
    const player = useRef<HTMLAudioElement>(null)
    const request = useRef<AbortController | null>(null)
    const urls = useRef<Record<string, string>>({})
    const selected = assets.find(asset => asset.id === value)
    useEffect(() => {
        if (!open) return
        const previous = document.activeElement as HTMLElement | null
        const audio = player.current
        dialog.current?.querySelector<HTMLInputElement>('input')?.focus()
        const keyboard = (event: KeyboardEvent) => {
            if (event.key === 'Escape') { event.preventDefault(); setOpen(false) }
            if (event.key !== 'Tab') return
            const elements = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, audio[controls]') || [])
            const first = elements[0], last = elements[elements.length - 1]
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
        }
        document.addEventListener('keydown', keyboard)
        return () => {
            document.removeEventListener('keydown', keyboard)
            request.current?.abort()
            audio?.pause()
            Object.values(urls.current).forEach(URL.revokeObjectURL)
            urls.current = {}
            previous?.focus()
        }
    }, [open])
    const play = async (asset: any) => {
        request.current?.abort()
        const controller = new AbortController()
        request.current = controller
        player.current?.pause()
        setBusy(asset.id); setError(''); setSample(asset.file_name)
        try {
            let url = urls.current[asset.id]
            if (!url) {
                const response = await fetch(`/api/std/projects/${encodeURIComponent(projectId)}/assets/file?assetId=${encodeURIComponent(asset.id)}`, {
                    headers, signal: controller.signal,
                })
                if (!response.ok) throw new Error('효과음 파일을 불러오지 못했습니다. 다시 시도해 주세요.')
                const blob = await response.blob()
                if (controller.signal.aborted) return
                if (!blob.size) throw new Error('효과음 파일이 비어 있습니다.')
                url = URL.createObjectURL(blob)
                urls.current[asset.id] = url
            }
            if (player.current && !controller.signal.aborted) {
                player.current.src = url
                player.current.volume = 0.7
                await player.current.play()
            }
        } catch (e: any) {
            if (!controller.signal.aborted) setError(e.message || '미리듣기에 실패했습니다.')
        } finally { if (!controller.signal.aborted) setBusy('') }
    }
    return <>
        <button type="button" disabled={disabled} onClick={() => {
            onOpen(); setDraft(value); setSearch(''); setError(''); setSample(''); setBusy(''); setOpen(true)
        }} className="flex w-full items-center gap-2 rounded-md border border-purple-500/40 bg-purple-500/10 p-2 text-left text-[11px] text-purple-100 hover:bg-purple-500/20 disabled:opacity-50">
            <span aria-hidden="true" className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-purple-400/50">★</span>
            <span className="shrink-0 font-bold">효과음 선택</span>
            {selected && <span className="min-w-0 truncate text-purple-300">{selected.file_name}</span>}
        </button>
        {open && createPortal(<div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/75 p-4" onClick={() => setOpen(false)}>
            <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="sfx-picker-title" onClick={event => event.stopPropagation()}
                className="flex max-h-[85dvh] w-full max-w-3xl flex-col gap-4 rounded-2xl border border-white/15 bg-[#1c2027] p-5 text-gray-100 shadow-2xl [color-scheme:dark]">
                <div className="flex items-center justify-between gap-3">
                    <h2 id="sfx-picker-title" className="text-base font-bold">효과음 선택 <span className="text-xs text-purple-300">{assets.length}개</span></h2>
                    <button type="button" aria-label="효과음 팝업 닫기" onClick={() => setOpen(false)} className="rounded px-2 py-1 text-gray-400 hover:bg-white/10">✕</button>
                </div>
                <input aria-label="효과음 검색" placeholder="효과음 이름 검색" value={search} onChange={event => setSearch(event.target.value)} className="w-full rounded-lg border border-white/10 bg-black/25 p-2.5 text-sm outline-none focus:border-purple-400" />
                <div className="grid min-h-0 grid-cols-1 gap-3 overflow-y-auto sm:grid-cols-2">
                    {assets.filter(asset => String(asset.file_name).toLowerCase().includes(search.toLowerCase())).map(asset => <div key={asset.id}
                        className={`min-w-0 rounded-xl border p-3 ${draft === asset.id ? 'border-purple-400 bg-purple-500/15' : 'border-white/10 bg-black/15'}`}>
                        <p className="break-all text-xs font-semibold leading-5">{asset.file_name}</p>
                        <div className="mt-3 flex items-center justify-between gap-2 text-xs">
                            <button type="button" disabled={busy === asset.id} onClick={() => void play(asset)} aria-label={`${asset.file_name} 미리듣기`} className="rounded border border-white/15 px-2.5 py-1.5 hover:bg-white/10 disabled:opacity-50">{busy === asset.id ? '불러오는 중…' : '▶ 미리듣기'}</button>
                            <button type="button" aria-pressed={draft === asset.id} onClick={() => setDraft(asset.id)} className="rounded bg-purple-500/20 px-2.5 py-1.5 text-purple-100">{draft === asset.id ? '✓ 선택됨' : '선택'}</button>
                        </div>
                    </div>)}
                    {!assets.length && <p className="py-5 text-sm text-gray-400 sm:col-span-2">배경음/효과음 탭에서 자막SFX를 업로드해 주세요.</p>}
                    {!!assets.length && !assets.some(asset => String(asset.file_name).toLowerCase().includes(search.toLowerCase())) && <p className="py-5 text-sm text-gray-400 sm:col-span-2">검색 결과가 없습니다.</p>}
                </div>
                <div className="shrink-0 space-y-2 rounded-xl bg-black/20 p-3">
                    <p className="truncate text-xs text-gray-400">{sample || '미리듣기 버튼을 눌러 효과음을 확인하세요.'}</p>
                    <audio ref={player} controls className="h-9 w-full" onError={() => setError('효과음 재생에 실패했습니다. 다른 파일을 선택해 주세요.')} />
                    {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
                </div>
                <div className="flex shrink-0 justify-end gap-2 text-xs">
                    <button type="button" onClick={() => { onChange(''); setOpen(false) }} className="mr-auto rounded px-3 py-2 text-gray-400 hover:bg-white/5">선택 해제</button>
                    <button type="button" onClick={() => setOpen(false)} className="rounded border border-white/10 px-4 py-2">취소</button>
                    <button type="button" disabled={!assets.some(asset => asset.id === draft)} onClick={() => { onChange(draft); setOpen(false) }} className="rounded bg-purple-600 px-4 py-2 font-bold text-white hover:bg-purple-500 disabled:opacity-40">선택 완료</button>
                </div>
            </div>
        </div>, document.body)}
    </>
}
