'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Mic, Play, Check, X } from 'lucide-react'
import { VOICE_STUDIO_VOICES, isVoiceStudioVoice } from '@/lib/voiceStudioCatalog'

type Voice = { id: string; name: string; gender?: string; category?: string; description?: string; preview_url?: string }
type Tab = 'narration' | 'dialogue'
type Props = {
    value: string; direction: string; onChange: (id: string, direction: string) => void; headers: Record<string, string>
    microphone?: boolean; label?: string; description?: string; buttonText?: string; voices?: Voice[]
    initialTab?: Tab; disabled?: boolean; open?: boolean; onOpenChange?: (open: boolean) => void
}
const genderName = (value?: string) => value === 'female' ? '여성' : value === 'male' ? '남성' : value || '미지정'

export default function VoiceStudioPicker({value, direction, onChange, headers, microphone = false, label, description, buttonText, voices = [], initialTab = 'narration', disabled = false, open: controlledOpen, onOpenChange}: Props) {
    const [localOpen, setLocalOpen] = useState(false)
    const open = controlledOpen ?? localOpen
    const [tab, setTab] = useState<Tab>(initialTab)
    const [search, setSearch] = useState(''), [gender, setGender] = useState('')
    const [draft, setDraft] = useState(value), [tone, setTone] = useState(direction)
    const [busy, setBusy] = useState(''), [error, setError] = useState(''), [previewName, setPreviewName] = useState('')
    const player = useRef<HTMLAudioElement>(null), urls = useRef<Record<string, string>>({})
    const request = useRef<AbortController | null>(null)
    const stopPreview = () => { request.current?.abort(); request.current = null; player.current?.pause(); if (player.current) player.current.removeAttribute('src'); setBusy(''); setPreviewName('') }
    const close = () => { stopPreview(); setLocalOpen(false); onOpenChange?.(false) }
    useEffect(() => () => { request.current?.abort(); Object.values(urls.current).forEach(URL.revokeObjectURL) }, [])
    useEffect(() => {
        if (!open) return
        const handler = (event: KeyboardEvent) => { if (event.key === 'Escape') close() }
        document.addEventListener('keydown', handler)
        return () => document.removeEventListener('keydown', handler)
    }, [open])
    const dialogueVoices = voices.filter(v => v.category !== 'google' && !v.id.startsWith('google') && !isVoiceStudioVoice(v.id))
    const available: Voice[] = tab === 'narration' ? VOICE_STUDIO_VOICES : dialogueVoices
    const selected = available.find(v => v.id === draft)
    const currentName = [...VOICE_STUDIO_VOICES, ...voices].find(v => v.id === value)?.name || value
    const filtered = available.filter(v => (!gender || genderName(v.gender) === gender) && `${v.name} ${v.description || ''}`.toLowerCase().includes(search.trim().toLowerCase()))
    const play = async (voice: Voice) => {
        stopPreview(); setError(''); setBusy(voice.id)
        const controller = new AbortController(); request.current = controller
        try {
            let url = voice.preview_url
            if (isVoiceStudioVoice(voice.id)) {
                if (!urls.current[voice.id]) {
                    const res = await fetch('/api/std/voice-studio/sample', {method:'POST', headers, signal:controller.signal, body:JSON.stringify({voice_id:voice.id})})
                    if (!res.ok) { const data = await res.json(); throw new Error(data.error || '샘플 생성 실패') }
                    const blob = await res.blob()
                    if (controller.signal.aborted) return
                    urls.current[voice.id] = URL.createObjectURL(blob)
                }
                url = urls.current[voice.id]
            }
            if (!url || controller.signal.aborted) return
            if (player.current) { player.current.src = url; setPreviewName(voice.name); await player.current.play() }
        } catch (e: any) { if (!controller.signal.aborted) setError(e.message || '미리듣기 실패') }
        finally { if (request.current === controller) { request.current = null; setBusy('') } }
    }
    return <>
        <button type="button" disabled={disabled} aria-label={label} title={label} onClick={event => {
            event.stopPropagation(); setDraft(value); setTone(direction); setTab(initialTab); setSearch(''); setGender(''); setError(''); setLocalOpen(true); onOpenChange?.(true)
        }} className={`${microphone ? `${buttonText ? 'px-2.5 gap-1.5' : 'w-8'} h-8 inline-flex items-center justify-center text-[10px]` : 'max-w-full truncate px-3 py-1.5 text-xs'} rounded-md border border-cyan-400/25 bg-[#10141b] text-cyan-100 font-bold hover:border-cyan-400/60 disabled:opacity-40 disabled:cursor-not-allowed`}>
            {microphone ? <><Mic size={14}/>{buttonText && <span>{buttonText}</span>}</> : buttonText || currentName}
        </button>
        {open && typeof document !== 'undefined' && createPortal(
            <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4" onClick={event => { event.stopPropagation(); close() }}>
                <div role="dialog" aria-modal="true" aria-label="목소리 선택" onClick={event => event.stopPropagation()} className="flex max-h-[90vh] w-full max-w-3xl flex-col gap-4 rounded-2xl border border-white/15 bg-[#1c2027] p-5 text-gray-100 shadow-2xl [color-scheme:dark]">
                    <div className="flex items-start justify-between gap-3"><div><h2 className="font-bold text-white">목소리 선택</h2><p className="mt-1 text-xs text-gray-400">현재 선택: <span className="text-cyan-200">{currentName || '없음'}</span></p></div><button type="button" onClick={close} aria-label="닫기" className="rounded-lg p-2 hover:bg-white/10"><X size={18}/></button></div>
                    {description && <p className="text-xs text-gray-400">{description}</p>}
                    <div role="tablist" aria-label="목소리 종류" className="grid grid-cols-2 gap-1 rounded-xl bg-black/25 p-1">
                        {([{id:'narration', name:'성우목소리', provider:'Google'}, {id:'dialogue', name:'대사목소리', provider:'ElevenLabs'}] as const).map(item => <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} onClick={() => {stopPreview(); setTab(item.id); setSearch(''); setGender(''); setError('')}} className={`rounded-lg px-3 py-2.5 text-sm font-bold transition ${tab === item.id ? 'bg-cyan-500/15 text-cyan-200 ring-1 ring-cyan-400/40' : 'text-gray-400 hover:text-white'}`}>{item.name}<span className="ml-2 text-[10px] opacity-70">{item.provider}</span></button>)}
                    </div>
                    <div className="flex gap-2"><input aria-label="목소리 검색" value={search} onChange={e => setSearch(e.target.value)} placeholder="목소리 이름, 설명 검색" className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-sm"/><select aria-label="성별" value={gender} onChange={e => setGender(e.target.value)} className="rounded-lg border border-white/10 bg-[#1c2027] px-3 text-xs"><option value="">성별 전체</option><option>남성</option><option>여성</option></select></div>
                    <div role="tabpanel" className="grid min-h-0 grid-cols-1 gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
                        {filtered.map(voice => <div key={voice.id} className={`flex min-h-40 flex-col rounded-xl border p-4 ${draft === voice.id ? 'border-cyan-400/70 bg-cyan-500/10' : 'border-white/10 bg-black/15'}`}>
                            <div className="flex items-start justify-between gap-2"><h3 title={voice.name} className="line-clamp-2 text-sm font-bold text-white">{voice.name}</h3><span className="shrink-0 rounded bg-white/10 px-2 py-0.5 text-[10px] text-gray-300">{genderName(voice.gender)}</span></div>
                            <p className="mb-4 mt-2 line-clamp-2 text-xs leading-relaxed text-gray-400">{voice.description || `${tab === 'narration' ? 'Google' : 'ElevenLabs'} · 샘플을 듣고 목소리를 선택하세요.`}</p>
                            <div className="mt-auto flex items-center justify-between gap-2"><button type="button" disabled={!!busy || (!isVoiceStudioVoice(voice.id) && !voice.preview_url)} onClick={() => void play(voice)} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs hover:bg-white/5 disabled:opacity-40"><Play size={12}/>{busy === voice.id ? '준비 중…' : '미리듣기'}</button><button type="button" aria-pressed={draft === voice.id} onClick={() => setDraft(voice.id)} className={`inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-bold ${draft === voice.id ? 'bg-cyan-500/20 text-cyan-200' : 'bg-white/5 text-gray-300 hover:bg-white/10'}`}>{draft === voice.id && <Check size={12}/>} {draft === voice.id ? '선택됨' : '선택'}</button></div>
                        </div>)}
                        {!filtered.length && <p className="col-span-full py-8 text-center text-sm text-gray-400">표시할 목소리가 없습니다.</p>}
                    </div>
                    <div className="rounded-xl border border-white/10 bg-black/15 p-3"><p className="mb-2 truncate text-xs text-gray-400">{previewName ? `미리듣기 · ${previewName}` : '카드의 미리듣기를 눌러 주세요.'}</p><audio ref={player} controls className="h-9 w-full"/></div>
                    {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
                    {tab === 'narration' && <label className="text-xs text-gray-400">말투·감정<input value={tone} maxLength={500} onChange={e => setTone(e.target.value)} placeholder="예: 담담하고 따뜻하게" className="mt-1 w-full rounded-lg border border-white/10 bg-black/25 p-2 text-gray-100"/></label>}
                    <div className="flex items-center justify-between gap-3"><span className="text-[10px] text-gray-500">{tab === 'narration' ? 'Google 샘플 최초 생성 시 Cloud 사용료가 발생합니다.' : 'ElevenLabs 제공 샘플'}</span><button type="button" disabled={!selected} onClick={() => {if (selected) {onChange(selected.id, isVoiceStudioVoice(selected.id) ? tone : ''); close()}}} className="shrink-0 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-40">선택 완료</button></div>
                </div>
            </div>, document.body
        )}
    </>
}
