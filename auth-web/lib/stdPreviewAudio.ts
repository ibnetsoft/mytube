import { isSubtitleClosingPunctuation } from './stdSubtitleFragments'

export function isSavedAudioRequiredError(error: any): boolean {
    return error?.code === 'audio_not_cached' || error?.code === 'audio_generation_claimed'
        || error?.status === 409
        || /중복 과금|저장 확인이 필요|audio_generation_claimed/.test(String(error?.message || ''))
}

export function savedAudioRequiredMessage(locale: string): string {
    const language = String(locale || '').toLowerCase().split(/[-_]/)[0]
    return ({
        ko: '이 구간의 음성을 준비 중이거나 아직 저장되지 않았습니다. 잠시 후 재생을 다시 눌러 주세요. 볼륨 변경은 별도로 저장됩니다.',
        en: 'Audio for this segment is being prepared or has not been saved yet. Please try playback again shortly.',
        th: 'เสียงส่วนนี้กำลังเตรียมหรือยังไม่ได้บันทึก โปรดลองเล่นอีกครั้งในอีกสักครู่',
        vi: 'Âm thanh đoạn này đang được chuẩn bị hoặc chưa được lưu. Vui lòng thử phát lại sau. Thay đổi âm lượng được lưu riêng.',
    } as Record<string, string>)[language] || 'Audio for this segment is being prepared or has not been saved yet. Please try playback again shortly.'
}

/** Generate only an explicitly previewed missing clip; wait for a concurrent owner without duplicating synthesis. */
export async function prepareScenePreviewClip(read: () => Promise<string>, generate: () => Promise<string>, pause: () => Promise<void>): Promise<string> {
    try { return await read() } catch (error: any) {
        if (error?.code !== 'audio_not_cached') throw error
    }
    try { return await generate() } catch (error: any) {
        if (error?.code !== 'audio_generation_claimed' && error?.status !== 409) throw error
        for (let attempt = 0; attempt < 8; attempt++) {
            await pause()
            try { return await read() } catch (retry: any) {
                if (retry?.code !== 'audio_not_cached') throw retry
            }
        }
        throw error
    }
}

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

// A stale/estimated MP3 duration must never block later subtitles or silently
// truncate the last line. Fall back to saved per-subtitle recordings instead.
export function narrationDurationMatchesTimeline(duration: number, subtitles: any[]): boolean {
    if (!Number.isFinite(duration) || duration <= 0 || !subtitles.length) return false
    const end = Number(subtitles[subtitles.length - 1].end_num ?? subtitles[subtitles.length - 1].end_time)
    return Number.isFinite(end) && end > 0 && Math.abs(duration - end) <= 0.15
}
