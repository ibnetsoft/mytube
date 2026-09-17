import type { DialoguePart } from './stdDialogueAnnotations'
export type SpeakerInfo = { name: string; gender: string; label: string }
export function normalizeSpeakerGender(value: unknown): string {
    const text = String(value || '').trim().toLowerCase()
    if (['male', 'man', '남성', '남자', 'ชาย'].includes(text)) return 'male'
    if (['female', 'woman', '여성', '여자', 'หญิง'].includes(text)) return 'female'
    return ''
}
// Editor metadata is never added to subtitle text or speech input.
export function subtitleSpeaker(subtitle: any, parts: DialoguePart[] | undefined, characters: any[]): SpeakerInfo | null {
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
    return { name, gender, label: character?.name_th ? `${name} / ${character.name_th}` : name }
}
export function assignSpeakerVoice(subtitles: any[], target: number, voiceId: string, voiceName: string, all: boolean, speakers: (SpeakerInfo | null)[]) {
    const name = speakers[target]?.name
    return subtitles.map((item, index) => index === target || (all && name && speakers[index]?.name === name)
        ? { ...item, voice_id: voiceId, voice_name: voiceName } : item)
}
