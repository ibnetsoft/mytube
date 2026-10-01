import { isSubtitleClosingPunctuation } from './stdSubtitleFragments'

// Loading a file is not playback: auxiliary tracks follow the narration media clock.
export function alignedNarrationSubtitles(subtitles: any[], timeline: any[], defaultVoice = ''): any[] | null {
    if (!Array.isArray(timeline) || !timeline.length || !subtitles.length) return null
    const normalized = (text: unknown) => String(text || '').replace(/\s+/g, '')
    let previousEnd = 0
    let cursor = 0
    const aligned = []
    for (const subtitle of subtitles) {
        const target = normalized(subtitle.text)
        const start = timeline[cursor]?.start
        let text = ''
        if (!target) return null
        do {
            const entry = timeline[cursor++]
            if (!entry || (!isSubtitleClosingPunctuation(String(entry.text || ''))
                && String(entry.voice_id) !== String(subtitle.voice_id || defaultVoice))
                || !Number.isFinite(entry.start) || !Number.isFinite(entry.end)
                || Math.abs(entry.start - previousEnd) > 0.05 || entry.end <= entry.start) return null
            text += normalized(entry.text)
            if (!target.startsWith(text)) return null
            previousEnd = entry.end
        } while (text !== target)
        aligned.push({ ...subtitle, start_num: start, end_num: previousEnd,
            start_time: start.toFixed(3), end_time: previousEnd.toFixed(3) })
    }
    return cursor === timeline.length ? aligned : null
}

export function bindNarrationPlayback(audio: HTMLAudioElement, onPlaying: () => void, onStopped: () => void) {
    audio.addEventListener('playing', onPlaying)
    const stops = ['waiting', 'pause', 'ended', 'error']
    stops.forEach(event => audio.addEventListener(event, onStopped))
    return () => {
        audio.removeEventListener('playing', onPlaying)
        stops.forEach(event => audio.removeEventListener(event, onStopped))
        onStopped()
    }
}

export function narrationLoadError(body: string, status: number) {
    if (/invalid_grant|drive_credentials_not_configured|drive_admin_credentials_incomplete/.test(body)) {
        return ''
    }
    return `저장된 음성 파일을 불러오지 못했습니다. (${status}) 잠시 후 다시 시도해 주세요.`
}

export async function resolveStoredSegmentAudio(
    request: (repairLegacy?: boolean) => Promise<any>,
    read: (payload: any) => Promise<string>,
    onRepair: () => void,
) {
    // Never spend TTS credits to repair a file access/authentication failure.
    const payload = await request()
    return await read(payload)
}
