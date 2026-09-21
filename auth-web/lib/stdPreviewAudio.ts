// Loading a file is not playback: auxiliary tracks follow the narration media clock.
export function alignedNarrationSubtitles(subtitles: any[], timeline: any[], defaultVoice = ''): any[] | null {
    if (!Array.isArray(timeline) || timeline.length !== subtitles.length || !timeline.length) return null
    const normalized = (text: unknown) => String(text || '').replace(/\s+/g, ' ').trim()
    let previousEnd = 0
    for (let i = 0; i < timeline.length; i++) {
        const entry = timeline[i]
        if (normalized(entry.text) !== normalized(subtitles[i].text)
            || String(entry.voice_id) !== String(subtitles[i].voice_id || defaultVoice)
            || !Number.isFinite(entry.start) || !Number.isFinite(entry.end)
            || Math.abs(entry.start - previousEnd) > 0.05 || entry.end <= entry.start) return null
        previousEnd = entry.end
    }
    return subtitles.map((subtitle, i) => ({ ...subtitle,
        start_num: timeline[i].start, end_num: timeline[i].end,
        start_time: timeline[i].start.toFixed(3), end_time: timeline[i].end.toFixed(3),
    }))
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
