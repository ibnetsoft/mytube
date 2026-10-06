'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { VOICE_STUDIO_VOICES, isVoiceStudioVoice } from '@/lib/voiceStudioCatalog'
import type { SupportedLocale } from '@/lib/i18n'
import { voiceDialogCopy } from '@/lib/voiceDialogLocale'
import { localizedVoiceDescription } from '@/lib/voiceDescriptionLocale'

function canonicalGender(gender?: string): 'male' | 'female' | 'neutral' | '' {
    const value = String(gender || '').trim().toLowerCase()
    if (['male', '남성', '남자', 'ชาย', 'nam'].includes(value)) return 'male'
    if (['female', '여성', '여자', 'หญิง', 'nữ'].includes(value)) return 'female'
    if (['neutral', 'non-binary', '중성', 'ไม่ระบุเพศ', 'trung tính'].includes(value)) return 'neutral'
    return ''
}

const sampleTimeLabel = (seconds: number) => {
    const time = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
    return `${Math.floor(time / 60)}:${String(time % 60).padStart(2, '0')}`
}

export type PickerVoice = { id: string; name?: string; gender?: string; description?: string; description_i18n?: Partial<Record<SupportedLocale, string>>; preview_url?: string; category?: string }
export default function UnifiedVoiceDialog({ value, direction = '', voices, initialTab, title, description, headers, onApply, onClose, editDirection = false, speakerContext, historyUserId, locale = 'ko' }: {
    locale?: SupportedLocale;
    speakerContext?: { name: string; gender: string; count: number; thai?: boolean };
    value: string; direction?: string; voices: PickerVoice[]; initialTab: 'google' | 'elevenlabs'; title: string;
    historyUserId?: string; description?: string; editDirection?: boolean; headers: Record<string, string>; onApply: (id: string, direction: string, allSpeaker?: boolean) => void | Promise<void>; onClose: () => void;
}) {
    const copy = voiceDialogCopy(locale)
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
    const [busy, setBusy] = useState(''), [error, setError] = useState<'' | 'sampleFailed' | 'noSample' | 'previewFailed' | 'saveFailed'>(''), [saving, setSaving] = useState(false)
    const [samplePlaying, setSamplePlaying] = useState(false)
    const [sampleTime, setSampleTime] = useState(0), [sampleDuration, setSampleDuration] = useState(0)
    const [sampleVolume, setSampleVolume] = useState(1)
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
            const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)') || [])
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
    const genderLabel = (v: PickerVoice) => {
        const gender = canonicalGender(v.gender)
        return gender ? copy[gender] : copy.genderUnknown
    }
    const voiceDescription = (v: PickerVoice) => localizedVoiceDescription(v, locale)
        || (isGoogle(v) ? copy.googleDescription : copy.elevenlabsDescription)
    const ranks = new Map(recent.map((id, index) => [id, index]))
    const visible = catalog.filter(v => (tab === 'google' ? isGoogle(v) : !isGoogle(v))
        && (!gender || canonicalGender(v.gender) === gender)
        && `${v.name || ''} ${voiceDescription(v)} ${v.description || ''} ${v.id}`.toLowerCase().includes(search.trim().toLowerCase()))
        .sort((a, b) => (ranks.get(a.id) ?? Infinity) - (ranks.get(b.id) ?? Infinity))
    const chosen = catalog.find(v => v.id === draft)
    const speakerGender = canonicalGender(speakerContext?.gender)
    const mismatch = Boolean(chosen && ((speakerGender === 'male' && canonicalGender(chosen.gender) === 'female') || (speakerGender === 'female' && canonicalGender(chosen.gender) === 'male')))
    const switchTab = (next: typeof tab) => {
        controller.current?.abort(); player.current?.pause(); setBusy(''); setError('')
        setTab(next); setSearch('')
    }
    const play = async (voice: PickerVoice) => {
        controller.current?.abort(); player.current?.pause()
        const request = new AbortController(); controller.current = request
        setBusy(voice.id); setError(''); setSampleTime(0); setSampleDuration(0)
        try {
            let url = voice.preview_url || ''
            if (isVoiceStudioVoice(voice.id)) {
                url = urls.current[voice.id]
                if (!url) {
                    const res = await fetch('/api/std/voice-studio/sample', { method: 'POST', headers,
                        signal: request.signal, body: JSON.stringify({ voice_id: voice.id }) })
                    if (!res.ok) throw new Error('sampleFailed')
                    const blob = await res.blob()
                    if (request.signal.aborted) return
                    url = URL.createObjectURL(blob); urls.current[voice.id] = url
                }
            }
            if (!url) throw new Error('noSample')
            if (player.current && !request.signal.aborted) { player.current.src = url; await player.current.play() }
        } catch (e: any) { if (!request.signal.aborted) setError(e?.message === 'sampleFailed' ? 'sampleFailed' : e?.message === 'noSample' ? 'noSample' : 'previewFailed') }
        finally { if (!request.signal.aborted) setBusy('') }
    }
    if (typeof document === 'undefined') return null
    return createPortal(<div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/70 p-4" onClick={e => { e.stopPropagation(); if (!saving) onClose() }}>
        <div ref={panel} lang={locale} role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()} className="flex max-h-[85dvh] w-full max-w-3xl flex-col gap-3 rounded-xl border border-white/20 bg-[#1c2027] p-5 text-gray-100 shadow-2xl [color-scheme:dark]">
            <div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-bold">{title}</h2><p className="mt-1 text-xs text-gray-400">{copy.currentVoice}: {catalog.find(v => v.id === value)?.name || value}</p></div><button type="button" disabled={saving} onClick={onClose} className="rounded border border-white/10 px-3 py-1 text-xs">{copy.close}</button></div>
            {description && <p className="text-xs text-gray-400">{description}</p>}
            {speakerContext && <div className="space-y-2 rounded-lg border border-cyan-400/25 bg-cyan-500/5 p-3 text-xs">
                <p className="font-bold">{copy.speaker}: {speakerContext.name || copy.speakerRequired} · {speakerGender ? copy[speakerGender] : copy.genderUnknown}</p>
                <p className="text-gray-400">{copy.speakerNote}</p>
                {speakerContext.name && speakerContext.count > 1 && <label className="flex items-center gap-2"><input type="checkbox" checked={allSpeaker} onChange={e => setAllSpeaker(e.target.checked)}/>{copy.applyAll(speakerContext.count)}</label>}
            </div>}
            <div role="tablist" aria-label={copy.providers} className="flex gap-2">
                {(['google', 'elevenlabs'] as const).map(provider => <button key={provider} type="button" role="tab" aria-selected={tab === provider} onClick={() => switchTab(provider)} className={`flex-1 rounded-lg border px-3 py-2 text-sm font-bold ${tab === provider ? 'border-cyan-400 bg-cyan-500/15 text-cyan-100' : 'border-white/10 text-gray-400'}`}>{provider === 'google' ? copy.google : copy.elevenlabs}</button>)}
            </div>
            <div className="flex flex-wrap gap-2"><input aria-label={copy.search} value={search} onChange={e => setSearch(e.target.value)} placeholder={copy.searchPlaceholder} className="min-w-0 flex-1 rounded border border-white/10 bg-black/25 p-2 text-sm"/>
                <div role="group" aria-label={copy.genderFilter} className="flex shrink-0 gap-1">
                    {(['', 'female', 'male'] as const).map(filter => <button key={filter} type="button" aria-pressed={gender === filter} onClick={() => setGender(filter)} className={`rounded border px-3 py-2 text-xs font-bold transition ${gender === filter ? 'border-cyan-400 bg-cyan-500/15 text-cyan-100' : 'border-white/10 text-gray-400 hover:border-cyan-400/50 hover:text-white'}`}>{filter ? copy[filter] : copy.all}</button>)}
                </div>
            </div>
            <div role="tabpanel" aria-label={tab === 'google' ? copy.google : copy.elevenlabs} className="grid min-h-0 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
                {visible.map(v => <div key={v.id} className={`flex flex-col rounded-lg border p-3 ${draft === v.id ? 'border-cyan-400 bg-cyan-500/15' : 'border-white/10 bg-black/15'}`}>
                    <p className="truncate text-sm font-bold" title={v.name}>{v.name || v.id}</p><p className="mt-1 text-[11px] text-gray-400">{genderLabel(v)}</p>
                    <p title={voiceDescription(v)} className="mt-2 line-clamp-2 min-h-8 text-[11px] text-gray-400">{voiceDescription(v)}</p>
                    <div className="mt-3 flex items-center justify-between gap-2 text-xs"><button type="button" disabled={busy === v.id || (!isVoiceStudioVoice(v.id) && !v.preview_url)} onClick={() => void play(v)} className="rounded border border-white/15 px-2 py-1.5 disabled:opacity-40">{busy === v.id ? copy.loading : copy.preview}</button><button type="button" aria-pressed={draft === v.id} onClick={() => { setDraft(v.id); setAllowMismatch(false) }} className="rounded bg-cyan-500/15 px-2 py-1.5">{draft === v.id ? copy.selected : copy.select}</button></div>
                </div>)}
                {!visible.length && <p className="col-span-full p-6 text-center text-sm text-gray-400">{copy.noResults}</p>}
            </div>
            <audio ref={player} className="hidden" onError={() => { setSamplePlaying(false); setError('previewFailed') }}
                onPlay={() => setSamplePlaying(true)} onPause={() => setSamplePlaying(false)} onEnded={() => setSamplePlaying(false)}
                onTimeUpdate={event => setSampleTime(event.currentTarget.currentTime)}
                onLoadedMetadata={event => setSampleDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)}
                onDurationChange={event => setSampleDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)} />
            <div role="group" aria-label={copy.preview} className="flex shrink-0 flex-wrap items-center gap-2 rounded-lg bg-black/20 p-2 text-xs">
                <button type="button" disabled={!sampleDuration && !samplePlaying} aria-label={samplePlaying ? copy.pause : copy.play}
                    title={samplePlaying ? copy.pause : copy.play} className="rounded border border-white/15 px-2 py-1 disabled:opacity-40"
                    onClick={() => { if (samplePlaying) player.current?.pause(); else void player.current?.play().catch(() => setError('previewFailed')) }}>
                    {samplePlaying ? copy.pause : copy.play}
                </button>
                <span className="whitespace-nowrap font-mono">{sampleTimeLabel(sampleTime)} / {sampleTimeLabel(sampleDuration)}</span>
                <input type="range" min={0} max={sampleDuration || 1} step={0.1} value={sampleTime} disabled={!sampleDuration}
                    aria-label={copy.seek} className="min-w-0 flex-1 accent-cyan-400" onChange={event => {
                        const time = Number(event.target.value)
                        if (player.current) player.current.currentTime = time
                        setSampleTime(time)
                    }} />
                <label className="flex items-center gap-1">{copy.volume}<input type="range" min={0} max={1} step={0.05} value={sampleVolume}
                    aria-label={copy.volume} className="w-16 accent-cyan-400" onChange={event => {
                        const volume = Number(event.target.value)
                        if (player.current) player.current.volume = volume
                        setSampleVolume(volume)
                    }} /></label>
            </div>
            {tab === 'google' && <p className="text-[11px] text-gray-400">{copy.googleSampleNote}</p>}
            {editDirection && isVoiceStudioVoice(draft) && <label className="text-xs">{copy.direction}<input value={tone} maxLength={500} onChange={e => setTone(e.target.value)} placeholder={copy.directionPlaceholder} className="mt-1 w-full rounded bg-black/25 p-2" /></label>}
            {mismatch && <div role="alert" className="space-y-2 rounded border border-amber-400/40 bg-amber-500/10 p-3 text-xs text-amber-200"><p>{copy.mismatch(speakerContext?.name || copy.speakerRequired, chosen?.name || '')}</p><label className="flex items-center gap-2"><input type="checkbox" checked={allowMismatch} onChange={e => setAllowMismatch(e.target.checked)}/>{copy.allowMismatch}</label></div>}
            {error && <p role="alert" className="text-xs text-red-300">{copy[error]}</p>}
            <div className="flex shrink-0 items-center justify-end gap-2 text-xs"><span className="mr-auto truncate text-cyan-200">{copy.selection}: {chosen?.name || copy.chooseVoice}</span><button type="button" disabled={saving} onClick={onClose} className="rounded border border-white/10 px-3 py-2">{copy.cancel}</button><button type="button" disabled={!chosen || saving || (mismatch && !allowMismatch)} onClick={async () => { setSaving(true); setError(''); try { await onApply(draft, tone, allSpeaker); rememberVoice(draft); onClose() } catch { setError('saveFailed') } finally { setSaving(false) } }} className="rounded bg-emerald-600 px-4 py-2 font-bold disabled:opacity-40">{saving ? copy.saving : copy.confirm}</button></div>
        </div>
    </div>, document.body)
}
