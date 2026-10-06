/** Apply recording times only when every saved row still matches its recording. */
export function applyRecordedSubtitleTiming(rows: any[], timeline: any[]): any[] {
    if (!Array.isArray(rows) || !rows.length || !Array.isArray(timeline) || !timeline.length) return rows
    if (rows.length !== timeline.length) throw new Error('자막 수가 녹음과 다릅니다. 최신 자막으로 TTS를 확정해 주세요.')
    return rows.map((row, i) => {
        const recorded = timeline[i]
        if (String(row.text || '').trim() !== String(recorded.text || '').trim()
            || String(row.voice_id || row.voiceId || '') !== String(recorded.voice_id || '')) {
            throw new Error(`${i + 1}번째 자막 또는 성우가 녹음과 다릅니다. 최신 자막으로 TTS를 확정해 주세요.`)
        }
        const start = Number(recorded.start), end = Number(recorded.end)
        if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) throw new Error('저장된 녹음 시간이 유효하지 않습니다.')
        const { restored_audio_pending, ...saved } = row
        return { ...saved, start, end, start_num: start, end_num: end,
            start_time: String(start), end_time: String(end) }
    })
}
