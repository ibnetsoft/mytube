'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { SupportedLocale } from '@/lib/i18n'
import { normalizeSpeakerGender, speakerNameLabel, type SpeakerInfo, type SpeakerNameTranslations } from '@/lib/stdSpeakerAssignment'

const COPY = {
    ko: {
        title: '화자 확인', note: '편집용 정보입니다. TTS와 영상 자막에는 포함되지 않습니다.',
        name: '화자 이름 (같은 인물은 같은 이름 사용)', gender: '인물 성별',
        unknown: '확인 필요', male: '남성', female: '여성', custom: '이름 직접 입력',
        placeholder: '원어 이름 입력', cancel: '취소', save: '저장', saving: '저장 중…', error: '저장에 실패했습니다.',
        translating: '이름을 한국어로 번역하고 있습니다…', translationError: '이름 번역을 불러오지 못했습니다.', retry: '다시 시도',
    },
    th: {
        title: 'ยืนยันผู้พูด', note: 'ข้อมูลสำหรับผู้ตัดต่อเท่านั้น ไม่อ่านออกเสียงและไม่แสดงในคำบรรยายวิดีโอ',
        name: 'ชื่อผู้พูด (ใช้ชื่อเดียวกันสำหรับตัวละครเดียวกัน)', gender: 'เพศของตัวละคร',
        unknown: 'ต้องยืนยัน', male: 'ชาย', female: 'หญิง', custom: 'กรอกชื่อเอง',
        placeholder: 'กรอกชื่อในภาษาต้นฉบับ', cancel: 'ยกเลิก', save: 'บันทึก', saving: 'กำลังบันทึก…', error: 'บันทึกไม่สำเร็จ',
        translating: 'กำลังแปลชื่อเป็นภาษาไทย…', translationError: 'โหลดคำแปลชื่อไม่สำเร็จ', retry: 'ลองอีกครั้ง',
    },
}

export default function SubtitleSpeakerEditor({ speaker, names, characters = [], locale = 'ko', translations = {},
    projectId, headers, onTranslations, onSave, onClose }: {
    speaker: SpeakerInfo | null; names: string[]; characters?: any[]; locale?: SupportedLocale;
    translations?: SpeakerNameTranslations; projectId?: string; headers?: Record<string, string>;
    onTranslations?: (locale: 'ko' | 'th', translations: Record<string, string>) => void;
    onSave: (name: string, gender: string) => Promise<void>; onClose: () => void;
}) {
    const copy = locale === 'th' ? COPY.th : COPY.ko
    const [name, setName] = useState(speaker?.name || '')
    const [custom, setCustom] = useState(false)
    const [gender, setGender] = useState(speaker?.gender || '')
    const [saving, setSaving] = useState(false), [error, setError] = useState(false)
    const [translated, setTranslated] = useState<SpeakerNameTranslations>({})
    const [translating, setTranslating] = useState(false), [translationError, setTranslationError] = useState(false)
    const [retry, setRetry] = useState(0)
    const onTranslationsRef = useRef(onTranslations)
    onTranslationsRef.current = onTranslations
    const optionNames = [...new Set([...names, speaker?.name || ''].map(value => value.trim()).filter(Boolean))]
    const namesKey = JSON.stringify(optionNames)
    const nameTranslations = { ...translations, [locale]: { ...translations[locale], ...translated[locale] } }

    useEffect(() => {
        if (!projectId || !headers || (locale !== 'ko' && locale !== 'th') || !optionNames.length) return
        const missing = optionNames.some(value => !characters.find(c => c.name === value)?.[`name_${locale}`]
            && !translations[locale]?.[value])
        if (!missing) return
        const controller = new AbortController()
        let timer: ReturnType<typeof setTimeout> | undefined
        setTranslating(true)
        setTranslationError(false)
        const load = async (jobId?: string) => {
            try {
                const response = await fetch(`/api/std/projects/${encodeURIComponent(projectId)}/speaker-translations`, {
                    method: 'POST', headers, signal: controller.signal,
                    body: JSON.stringify({ target_language: locale, names: optionNames, ...(jobId ? { job_id: jobId } : {}) }),
                })
                const result = await response.json()
                if (!response.ok || !result.success) throw new Error('Name translation failed')
                if (controller.signal.aborted) return
                const values = result.translations || {}
                setTranslated(previous => ({ ...previous, [locale]: { ...previous[locale], ...values } }))
                if (result.pending && result.job_id) {
                    timer = setTimeout(() => void load(result.job_id), 3000)
                    return
                }
                setTranslating(false)
                onTranslationsRef.current?.(locale, values)
            } catch {
                if (!controller.signal.aborted) {
                    setTranslating(false)
                    setTranslationError(true)
                }
            }
        }
        void load()
        return () => { controller.abort(); if (timer) clearTimeout(timer) }
    }, [projectId, locale, namesKey, headers, retry])

    const chooseName = (value: string) => {
        setCustom(false)
        setName(value)
        const character = characters.find(c => String(c.name || '').trim() === value)
        setGender(value === speaker?.name ? speaker.gender : normalizeSpeakerGender(character?.gender))
    }
    const radioStyle = (selected: boolean, value = '') => selected
        ? value === 'female' ? 'border-pink-400/50 bg-pink-500/15 text-pink-200'
            : value === 'male' ? 'border-sky-200 bg-sky-300/90 text-sky-950'
                : 'border-cyan-400/50 bg-cyan-500/10 text-cyan-100'
        : 'border-white/10 bg-black/15 text-gray-200 hover:border-white/30'

    return createPortal(<div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4" onClick={e => e.stopPropagation()}>
        <div role="dialog" aria-modal="true" aria-label={copy.title} lang={locale === 'th' ? 'th' : 'ko'}
            className="flex max-h-[85dvh] w-full max-w-lg flex-col gap-4 overflow-y-auto rounded-xl border border-white/20 bg-[#1c2027] p-5 text-gray-100">
            <h2 className="font-bold">{copy.title}</h2>
            <p className="text-xs text-gray-400">{copy.note}</p>
            <fieldset disabled={saving} className="min-w-0 space-y-2">
                <legend className="mb-2 text-sm font-semibold">{copy.name}</legend>
                <div className="max-h-64 space-y-2 overflow-y-auto">
                    {optionNames.map(value => <label key={value} className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-sm ${radioStyle(!custom && name === value)}`}>
                        <input type="radio" name="subtitle-speaker-name" value={value} checked={!custom && name === value}
                            onChange={() => chooseName(value)} className="h-4 w-4 shrink-0 accent-sky-400" />
                        <span className="break-words">{speakerNameLabel(value, characters, locale, nameTranslations)}</span>
                    </label>)}
                    <label className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-sm ${radioStyle(custom)}`}>
                        <input type="radio" name="subtitle-speaker-name" value="__custom__" checked={custom}
                            onChange={() => { setCustom(true); setName(''); setGender('') }} className="h-4 w-4 accent-sky-400" />
                        {copy.custom}
                    </label>
                </div>
                {custom && <input aria-label={copy.custom} placeholder={copy.placeholder} value={name} maxLength={80}
                    onChange={e => setName(e.target.value)} className="w-full rounded-lg border border-white/20 bg-black/30 p-2 text-sm" />}
            </fieldset>
            {translating && <p role="status" className="text-xs text-gray-400">{copy.translating}</p>}
            {translationError && <p role="alert" className="text-xs text-amber-200">{copy.translationError} <button type="button"
                onClick={() => setRetry(value => value + 1)} className="underline">{copy.retry}</button></p>}
            <fieldset disabled={saving}>
                <legend className="mb-2 text-sm font-semibold">{copy.gender}</legend>
                <div className="flex flex-wrap gap-2">
                    {([['', copy.unknown], ['male', copy.male], ['female', copy.female]] as const).map(([value, label]) => <label key={value}
                        className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${radioStyle(gender === value, value)}`}>
                        <input type="radio" name="subtitle-speaker-gender" value={value} checked={gender === value}
                            onChange={() => setGender(value)} className={`h-4 w-4 ${value === 'female' ? 'accent-pink-400' : value === 'male' ? 'accent-sky-800' : 'accent-sky-400'}`} />
                        {label}
                    </label>)}
                </div>
            </fieldset>
            {error && <p role="alert" className="text-red-300">{copy.error}</p>}
            <div className="flex justify-end gap-2">
                <button type="button" disabled={saving} onClick={onClose} className="rounded-lg border border-white/10 px-4 py-2 text-sm disabled:opacity-40">{copy.cancel}</button>
                <button type="button" disabled={saving || !name.trim()} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold disabled:opacity-40"
                    onClick={async () => { setSaving(true); setError(false); try { await onSave(name.trim(), gender); onClose() } catch { setError(true) } finally { setSaving(false) } }}>
                    {saving ? copy.saving : copy.save}
                </button>
            </div>
        </div>
    </div>, document.body)
}
