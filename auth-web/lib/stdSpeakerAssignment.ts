import type { DialoguePart } from './stdDialogueAnnotations'
import type { SupportedLocale } from './i18n'
export type SpeakerInfo = { name: string; gender: string; label: string }
export type SpeakerNameTranslations = Partial<Record<SupportedLocale, Record<string, string>>>

export function speakerNameLabel(name: string, characters: any[], locale: SupportedLocale, translations: SpeakerNameTranslations = {}): string {
    const character = characters.find(c => String(c.name || '').trim() === name)
    const localized = String(character?.[`name_${locale}`] || translations[locale]?.[name] || '').trim()
    return localized && localized !== name ? `${name} (${localized})` : name
}
export function normalizeSpeakerGender(value: unknown): string {
    const text = String(value || '').trim().toLowerCase()
    if (['male', 'man', '남성', '남자', 'ชาย'].includes(text)) return 'male'
    if (['female', 'woman', '여성', '여자', 'หญิง'].includes(text)) return 'female'
    return ''
}
// Editor metadata is never added to subtitle text or speech input.
export function subtitleSpeaker(subtitle: any, parts: DialoguePart[] | undefined, characters: any[], locale: SupportedLocale = 'ko', translations: SpeakerNameTranslations = {}): SpeakerInfo | null {
    const manual = subtitle?.editor_speaker
    let name = ''
    if (manual && manual.text === subtitle.text) name = String(manual.name || '').trim()
    else {
        const speakers = [...new Set((parts || []).filter(p => p.dialogue && p.speaker).map(p => p.speaker!))]
        if (speakers.length !== 1 || parts?.some(p => !p.dialogue && p.text.replace(/[\s"'“”‘’「」『』]/g, ''))) return null
        name = speakers[0]
    }
    if (!name) return null
    const character = characters.find(c => String(c.name || '').trim() === name)
    const gender = normalizeSpeakerGender(manual?.text === subtitle.text ? manual.gender : character?.gender)
    return { name, gender, label: speakerNameLabel(name, characters, locale, translations) }
}
export function assignSpeakerVoice(subtitles: any[], target: number, voiceId: string, voiceName: string, all: boolean, speakers: (SpeakerInfo | null)[]) {
    const name = speakers[target]?.name
    return subtitles.map((item, index) => index === target || (all && name && speakers[index]?.name === name)
        ? { ...item, voice_id: voiceId, voice_name: voiceName } : item)
}

type SpeakerVoiceSource = { voice_map?: Record<string, unknown>; voice_id?: unknown; explicit?: boolean }

// Resolve identity across the project, never from a translated label or the row's fallback narrator.
export function confirmSubtitleSpeaker(subtitles: any[], target: number, name: string, gender: string,
    speakers: (SpeakerInfo | null)[], voiceNameById: ReadonlyMap<string, string>, voiceSources: SpeakerVoiceSource[] = []) {
    name = name.trim()
    if (!name || !subtitles[target]) return { subtitles, voiceId: null, conflict: false }
    const text = (value: unknown) => typeof value === 'string' ? value.trim() : ''
    const mappedVoice = (source: SpeakerVoiceSource) => {
        const id = text(source.voice_map?.[name])
        // Legacy TTS maps contain the narrator for every character without a selection.
        return id && (source.explicit || id !== text(source.voice_id)) ? id : ''
    }
    const donors = subtitles.filter((row, index) => index !== target && row.dialogue_override !== false
        && speakers[index]?.name === name && text(row.voice_id)
        && (!row.editor_speaker || row.editor_speaker.text === row.text))
    const ids = [...new Set(donors.map(row => text(row.voice_id)))]
    const explicitVoice = voiceSources.filter(source => source.explicit).map(mappedVoice).find(Boolean)
    const conflict = !explicitVoice && ids.length > 1
    const voiceId = explicitVoice || (ids.length === 1 ? ids[0] : '')
        || (!conflict ? voiceSources.filter(source => !source.explicit).map(mappedVoice).find(Boolean) : '') || null
    const donor = donors.find(row => text(row.voice_id) === voiceId)
    const voiceName = voiceId ? voiceNameById.get(voiceId) || text(donor?.voice_name) || voiceId : ''
    const updated = subtitles.map((row, index) => {
        if (index !== target && (row.dialogue_override === false || speakers[index]?.name !== name)) return row
        return {
            ...row,
            editor_speaker: { name, gender, text: row.text },
            ...(voiceId && (index === target || !text(row.voice_id)) ? { voice_id: voiceId, voice_name: voiceName } : {}),
        }
    })
    return { subtitles: updated, voiceId, conflict }
}
