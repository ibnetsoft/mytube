export function audioWaveformPeaks(channels: Float32Array[], count = 160): number[] {
    const length = channels[0]?.length || 0
    if (!length || count < 1) return []
    const bins = Math.min(Math.floor(count), length)
    return Array.from({ length: bins }, (_, index) => {
        const start = Math.floor(index * length / bins)
        const end = Math.floor((index + 1) * length / bins)
        let peak = 0
        for (const channel of channels) {
            for (let i = start; i < end; i++) peak = Math.max(peak, Math.abs(channel[i] || 0))
        }
        return Math.min(1, peak)
    })
}

export function backgroundTrackPosition(time: number, duration: number, loop = true): number {
    return duration > 0 && Number.isFinite(time)
        ? loop ? Math.max(0, time) % duration : Math.min(duration, Math.max(0, time))
        : 0
}
