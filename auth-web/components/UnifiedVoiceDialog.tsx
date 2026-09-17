'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { VOICE_STUDIO_VOICES, isVoiceStudioVoice } from '@/lib/voiceStudioCatalog'

export type PickerVoice = { id: string; name?: string; gender?: string; description?: string; preview_url?: string; category?: string }
export default function UnifiedVoiceDialog({ value, direction = '', voices, initialTab, title, description, headers, onApply, onClose, editDirection = false, speakerContext, historyUserId }: {
    speakerContext?: { name: string; gender: string; count: number; thai: boolean };
    value: string; direction?: string; voices: PickerVoice[]; initialTab: 'google' | 'elevenlabs'; title: string;
    historyUserId?: string; description?: string; editDirection?: boolean; headers: Record<string, string>; onApply: (id: string, direction: string, allSpeaker?: boolean) => void | Promise<void>; onClose: () => void;
}) {
    const historyKey = historyUserId ? `air:recent-voices:v1:${historyUserId}` : ''
    const readHistory = (): string[] => {
        try {
            const stored = historyKey ? JSON.parse(localStorage.getItem(historyKey) || '[]') : []
            return Array.isArray(stored) ? [...new Set(stored.filter((id): id is string => typeof id === 'string'))].slice(0, 200) : []
        } catch { return [] }
    }
    const [recent, setRecent] = useState<string[]>([])
    useEffect(() => { setRecent(readHistory()) }, [historyKey])
    const rememberVoice = (id: string) => {
        if (!historyKey) return
        const next = [id, ...readHistory().filter(previous => previous !== id)].slice(0, 200)
        try { localStorage.setItem(historyKey, JSON.stringify(next)) } catch { /* Storage may be disabled. Voice application still succeeds. */ }
    }
    const [allSpeaker, setAllSpeaker] = useState(Boolean(speakerContext?.name && speakerContext.count > 1))
    const [allowMismatch, setAllowMismatch] = useState(false)
    const [tab, setTab] = useState(initialTab)
    const [draft, setDraft] = useState(value), [tone, setTone] = useState(direction)
    const [search, setSearch] = useState(''), [gender, setGender] = useState('')
    const [busy, setBusy] = useState(''), [error, setError] = useState(''), [saving, setSaving] = useState(false)
    const player = useRef<HTMLAudioElement>(null), panel = useRef<HTMLDivElement>(null)
    const controller = useRef<AbortController | null>(null), urls = useRef<Record<string, string>>({})
    const closeRef = useRef(onClose); closeRef.current = () => { if (!saving) onClose() }
    useEffect(() => {
        const previous = document.activeElement as HTMLElement | null
        const audio = player.current
        panel.current?.querySelector<HTMLInputElement>('input')?.focus()
        const keydown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') { e.preventDefault(); closeRef.current() }
            if (e.key !== 'Tab') return
            const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, audio[controls]') || [])
            const first = items[0], last = items[items.length - 1]
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
        }
        document.addEventListener('keydown', keydown)
        return () => {
            document.removeEventListener('keydown', keydown)
            controller.current?.abort(); audio?.pause()
            Object.values(urls.current).forEach(URL.revokeObjectURL)
            previous?.focus()
        }
    }, [])
    const isGoogle = (v: PickerVoice) => isVoiceStudioVoice(v.id) || v.id.toLowerCase().startsWith('google') || v.category === 'google'
    const catalog: PickerVoice[] = [...new Map([...VOICE_STUDIO_VOICES, ...voices].map(v => [v.id, v])).values()]
    const genderLabel = (v: PickerVoice) => v.gender === 'male' ? '남성' : v.gender === 'female' ? '여성' : v.gender || ''
    const ranks = new Map(recent.map((id, index) => [id, index]))
    const visible = catalog.filter(v => (tab === 'google' ? isGoogle(v) : !isGoogle(v))
        && (!gender || genderLabel(v) === gender)
        && `${v.name || ''} ${v.description || ''} ${v.id}`.toLowerCase().includes(search.trim().toLowerCase()))
        .sort((a, b) => (ranks.get(a.id) ?? Infinity) - (ranks.get(b.id) ?? Infinity))
    const chosen = catalog.find(v => v.id === draft)
    const mismatch = Boolean(speakerContext?.gender && chosen && ((speakerContext.gender === 'male' && genderLabel(chosen) === '여성') || (speakerContext.gender === 'female' && genderLabel(chosen) === '남성')))
    const switchTab = (next: typeof tab) => {
        controller.current?.abort(); player.current?.pause(); setBusy(''); setError('')
        setTab(next); setSearch('')
    }
    const play = async (voice: PickerVoice) => {
        controller.current?.abort(); player.current?.pause()
        const request = new AbortController(); controller.current = request
        setBusy(voice.id); setError('')
        try {
            let url = voice.preview_url || ''
            if (isVoiceStudioVoice(voice.id)) {
                url = urls.current[voice.id]
                if (!url) {
                    const res = await fetch('/api/std/voice-studio/sample', { method: 'POST', headers,
                        signal: request.signal, body: JSON.stringify({ voice_id: voice.id }) })
                    if (!res.ok) throw new Error('샘플을 불러오지 못했습니다. 다시 시도해 주세요.')
                    const blob = await res.blob()
                    if (request.signal.aborted) return
                    url = URL.createObjectURL(blob); urls.current[voice.id] = url
                }
            }
            if (!url) throw new Error('제공된 미리듣기 샘플이 없습니다.')
            if (player.current && !request.signal.aborted) { player.current.src = url; await player.current.play() }
        } catch (e: any) { if (!request.signal.aborted) setError(e.message || '미리듣기에 실패했습니다.') }
        finally { if (!request.signal.aborted) setBusy('') }
    }
    if (typeof document === 'undefined') return null
    return createPortal(<div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/70 p-4" onClick={e => { e.stopPropagation(); if (!saving) onClose() }}>
        <div ref={panel} role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()} className="flex max-h-[85dvh] w-full max-w-3xl flex-col gap-3 rounded-xl border border-white/20 bg-[#1c2027] p-5 text-gray-100 shadow-2xl [color-scheme:dark]">
            <div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-bold">{title}</h2><p className="mt-1 text-xs text-gray-400">현재 성우: {catalog.find(v => v.id === value)?.name || value}</p></div><button type="button" disabled={saving} onClick={onClose} className="rounded border border-white/10 px-3 py-1 text-xs">닫기</button></div>
            {description && <p className="text-xs text-gray-400">{description}</p>}
            {speakerContext && <div className="space-y-2 rounded-lg border border-cyan-400/25 bg-cyan-500/5 p-3 text-xs">
                <p className="font-bold">{speakerContext.thai ? 'ผู้พูด' : '화자'}: {speakerContext.name || (speakerContext.thai ? 'ต้องยืนยันผู้พูดก่อน' : '화자 확인 필요')} · {speakerContext.gender === 'male' ? (speakerContext.thai ? 'ชาย' : '남성') : speakerContext.gender === 'female' ? (speakerContext.thai ? 'หญิง' : '여성') : (speakerContext.thai ? 'ยังไม่ยืนยันเพศ' : '성별 확인 필요')}</p>
                <p className="text-gray-400">{speakerContext.thai ? 'ข้อมูลสำหรับผู้ตัดต่อเท่านั้น ไม่อ่านชื่อและไม่ใส่ชื่อในคำบรรยายวิดีโอ' : '화자 정보는 편집용이며 TTS·영상 자막에 포함되지 않습니다.'}</p>
                {speakerContext.name && speakerContext.count > 1 && <label className="flex items-center gap-2"><input type="checkbox" checked={allSpeaker} onChange={e => setAllSpeaker(e.target.checked)}/>{speakerContext.thai ? `ใช้เสียงนี้กับบทพูดทั้งหมดของตัวละครนี้ (${speakerContext.count})` : `이 인물의 모든 대사 ${speakerContext.count}개에 적용`}</label>}
            </div>}
            <div role="tablist" aria-label="성우 제공사" className="flex gap-2">
                {(['google', 'elevenlabs'] as const).map(provider => <button key={provider} type="button" role="tab" aria-selected={tab === provider} onClick={() => switchTab(provider)} className={`flex-1 rounded-lg border px-3 py-2 text-sm font-bold ${tab === provider ? 'border-cyan-400 bg-cyan-500/15 text-cyan-100' : 'border-white/10 text-gray-400'}`}>{provider === 'google' ? 'Google 성우' : 'ElevenLabs 성우'}</button>)}
            </div>
            <div className="flex flex-wrap gap-2"><input aria-label="성우 검색" value={search} onChange={e => setSearch(e.target.value)} placeholder="성우 이름, 설명 검색" className="min-w-0 flex-1 rounded border border-white/10 bg-black/25 p-2 text-sm"/>
                <div role="group" aria-label="성별 필터" className="flex shrink-0 gap-1">
                    {['', '여성', '남성'].map(filter => <button key={filter} type="button" aria-pressed={gender === filter} onClick={() => setGender(filter)} className={`rounded border px-3 py-2 text-xs font-bold transition ${gender === filter ? 'border-cyan-400 bg-cyan-500/15 text-cyan-100' : 'border-white/10 text-gray-400 hover:border-cyan-400/50 hover:text-white'}`}>{speakerContext?.thai ? (filter === '여성' ? 'หญิง' : filter === '남성' ? 'ชาย' : 'ทั้งหมด') : filter || '전체'}</button>)}
                </div>
            </div>
            <div role="tabpanel" aria-label={tab === 'google' ? 'Google 성우' : 'ElevenLabs 성우'} className="grid min-h-0 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
                {visible.map(v => <div key={v.id} className={`flex flex-col rounded-lg border p-3 ${draft === v.id ? 'border-cyan-400 bg-cyan-500/15' : 'border-white/10 bg-black/15'}`}>
                    <p className="truncate text-sm font-bold" title={v.name}>{v.name || v.id}</p><p className="mt-1 text-[11px] text-gray-400">{genderLabel(v) || '성별 미지정'}</p>
                    <p className="mt-2 line-clamp-2 min-h-8 text-[11px] text-gray-400">{v.description || (isGoogle(v) ? 'Google 음성' : 'ElevenLabs 음성')}</p>
                    <div className="mt-3 flex items-center justify-between gap-2 text-xs"><button type="button" disabled={busy === v.id || (!isVoiceStudioVoice(v.id) && !v.preview_url)} onClick={() => void play(v)} className="rounded border border-white/15 px-2 py-1.5 disabled:opacity-40">{busy === v.id ? '불러오는 중…' : '▶ 미리듣기'}</button><button type="button" aria-pressed={draft === v.id} onClick={() => { setDraft(v.id); setAllowMismatch(false) }} className="rounded bg-cyan-500/15 px-2 py-1.5">{draft === v.id ? '✓ 선택됨' : '선택'}</button></div>
                </div>)}
                {!visible.length && <p className="col-span-full p-6 text-center text-sm text-gray-400">검색 결과가 없습니다.</p>}
            </div>
            <audio ref={player} controls className="h-9 w-full shrink-0" onError={() => setError('미리듣기를 재생하지 못했습니다.')} />
            {tab === 'google' && <p className="text-[11px] text-gray-400">Google 샘플은 미리듣기를 누를 때만 요청하며, 최초 생성 시 사용료가 발생할 수 있습니다.</p>}
            {editDirection && isVoiceStudioVoice(draft) && <label className="text-xs">말투·감정<input value={tone} maxLength={500} onChange={e => setTone(e.target.value)} placeholder="예: 담담하고 따뜻하게" className="mt-1 w-full rounded bg-black/25 p-2" /></label>}
            {mismatch && <div role="alert" className="space-y-2 rounded border border-amber-400/40 bg-amber-500/10 p-3 text-xs text-amber-200"><p>{speakerContext?.thai ? `เพศของเสียง ${chosen?.name} ไม่ตรงกับตัวละคร ${speakerContext.name}` : `${speakerContext?.name}의 성별과 선택한 성우 ${chosen?.name}의 성별이 다릅니다.`}</p><label className="flex items-center gap-2"><input type="checkbox" checked={allowMismatch} onChange={e => setAllowMismatch(e.target.checked)}/>{speakerContext?.thai ? 'ยืนยันว่าเลือกเสียงต่างเพศโดยตั้งใจ' : '의도적으로 다른 성별의 성우를 사용합니다'}</label></div>}
            {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
            <div className="flex shrink-0 items-center justify-end gap-2 text-xs"><span className="mr-auto truncate text-cyan-200">선택: {chosen?.name || '성우를 선택해 주세요'}</span><button type="button" disabled={saving} onClick={onClose} className="rounded border border-white/10 px-3 py-2">취소</button><button type="button" disabled={!chosen || saving || (mismatch && !allowMismatch)} onClick={async () => { setSaving(true); setError(''); try { await onApply(draft, tone, allSpeaker); rememberVoice(draft); onClose() } catch { setError('성우 저장에 실패했습니다. 다시 시도해 주세요.') } finally { setSaving(false) } }} className="rounded bg-emerald-600 px-4 py-2 font-bold disabled:opacity-40">{saving ? '저장 중…' : '선택 완료'}</button></div>
        </div>
    </div>, document.body)
}
