// Keep this policy in sync with services/speech_gain.py. Leave 6 dB of
// headroom so the editor's 200% setting can amplify without clipping.
export function subtitleGain(subtitle: any): number {
    const value = Number(subtitle?.volume ?? (subtitle?.volume_ratio != null ? subtitle.volume_ratio * 100 : 100))
    return Number.isFinite(value) ? Math.max(0, Math.min(2, value / 100)) : 1
}

export function speechNormalization(channels: Float32Array[], start = 0, end = channels[0]?.length || 0): number {
    let energy = 0, count = 0, peak = 0
    for (const channel of channels) {
        for (let i = Math.max(0, start); i < Math.min(end, channel.length); i++) {
            const sample = Math.abs(channel[i])
            peak = Math.max(peak, sample)
            if (sample > 0.00316227766) { energy += sample * sample; count++ }
        }
    }
    if (!count || !peak) return 1
    return Math.min(4, Math.pow(10, -23 / 20) / Math.sqrt(energy / count), Math.pow(10, -7 / 20) / peak)
}

const analysisCache = new Map<string, Promise<number[]>>()

export function prepareSpeechPlayback(context: AudioContext, url: string, subtitles: any[]) {
    const key = JSON.stringify([url, subtitles.map(s => [s.start_num ?? s.start_time, s.end_num ?? s.end_time])])
    const existing = analysisCache.get(key)
    if (existing) return existing
    const pending = analyzeSpeech(context, url, subtitles).catch(error => {
        analysisCache.delete(key)
        throw error
    })
    // Retain only small gain arrays, never decoded longform PCM buffers.
    if (analysisCache.size >= 8) analysisCache.delete(analysisCache.keys().next().value!)
    analysisCache.set(key, pending)
    return pending
}

async function analyzeSpeech(context: AudioContext, url: string, subtitles: any[]) {
    const response = await fetch(url)
    if (!response.ok) throw new Error('음성 볼륨 분석용 파일을 불러오지 못했습니다.')
    const buffer = await context.decodeAudioData(await response.arrayBuffer())
    const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i))
    return subtitles.map(subtitle => speechNormalization(channels,
        Math.floor(Number(subtitle.start_num ?? subtitle.start_time ?? 0) * buffer.sampleRate),
        Math.floor(Number(subtitle.end_num ?? subtitle.end_time ?? buffer.duration) * buffer.sampleRate)))
}

export function connectSpeechGain(context: AudioContext, audio: HTMLAudioElement) {
    const source = context.createMediaElementSource(audio)
    const gain = context.createGain()
    source.connect(gain).connect(context.destination)
    return {
        set: (value: number) => { gain.gain.value = value },
        dispose: () => { source.disconnect(); gain.disconnect() },
    }
}
