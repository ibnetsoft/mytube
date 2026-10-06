'use client'
import { useEffect, useMemo, useRef, useState } from 'react'
import { resolveSfxCues } from '@/lib/stdSfxCues'
import { audioWaveformPeaks } from '@/lib/audioWaveform'

function SfxTrack({ cue, asset, projectId, headers, time, playing, onError, audioContextRef, subtitles }: any) {
    const [decoded, setDecoded] = useState<{ buffer: AudioBuffer } | null>(null)
    const [error, setError] = useState('')
    const running = useRef<{ source: AudioBufferSourceNode; gain: GainNode; context: AudioContext; clock: number; offset: number } | null>(null)
    const fallbackContext = useRef<AudioContext | null>(null)
    const report = useRef(onError)
    report.current = onError
    const headersKey = JSON.stringify(headers)
    const stop = () => {
        const current = running.current
        running.current = null
        if (current) { try { current.source.stop() } catch {} current.source.disconnect(); current.gain.disconnect() }
    }
    useEffect(() => {
        stop(); setDecoded(null); setError('')
        if (!asset?.id) { setError('효과음 파일을 찾을 수 없습니다.'); return }
        const controller = new AbortController()
        void (async () => {
            try {
                // Use the same authenticated asset path as standalone preview, including GCS assets.
                const response = await fetch(`/api/std/projects/${projectId}/assets/file?assetId=${encodeURIComponent(asset.id)}`, {
                    headers: JSON.parse(headersKey), signal: controller.signal,
                })
                if (!response.ok) throw new Error('효과음 파일을 불러오지 못했습니다.')
                const encoded = await response.arrayBuffer()
                if (controller.signal.aborted) return
                const buffer = await new OfflineAudioContext(1, 1, 22050).decodeAudioData(encoded)
                if (!controller.signal.aborted) setDecoded({ buffer })
            } catch (e: any) {
                if (!controller.signal.aborted) { setError(e.message || '효과음 파일 해독에 실패했습니다.'); report.current(e.message) }
            }
        })()
        return () => { controller.abort(); stop() }
    }, [asset?.id, projectId, headersKey])
    const duration = decoded ? Math.min(decoded.buffer.duration, Number(cue.duration) > 0 ? Number(cue.duration) : decoded.buffer.duration) : Number(cue.duration) || 0
    const offset = time - Number(cue.start || 0)
    useEffect(() => {
        if (!decoded || !playing || offset < 0 || offset >= duration) { stop(); return }
        const context = audioContextRef?.current || fallbackContext.current || new AudioContext()
        if (!audioContextRef?.current) fallbackContext.current = context
        const current = running.current
        const gainValue = Math.min(1, Math.pow(10, Number(cue.volume_db ?? -18) / 20))
        if (current && current.context === context && Math.abs(current.offset + context.currentTime - current.clock - offset) < 0.3) {
            current.gain.gain.value = gainValue
            return
        }
        stop()
        if (context.state === 'suspended') void context.resume().catch(() => {
            setError('효과음 오디오 재생이 차단됐습니다. 재생 버튼을 다시 눌러 주세요.')
        })
        try {
            const source = context.createBufferSource(), gain = context.createGain()
            source.buffer = decoded.buffer; gain.gain.value = gainValue
            source.connect(gain).connect(context.destination)
            running.current = { source, gain, context, clock: context.currentTime, offset }
            source.start(0, offset, duration - offset)
            source.onended = () => { if (running.current?.source === source) { running.current = null; source.disconnect(); gain.disconnect() } }
        } catch {
            stop(); setError('효과음 재생에 실패했습니다.'); report.current('효과음 재생에 실패했습니다.')
        }
    }, [decoded, playing, time, cue.start, cue.volume_db, duration, audioContextRef])
    useEffect(() => () => { stop(); void fallbackContext.current?.close() }, [])
    const displayedPeaks = useMemo(() => decoded ? audioWaveformPeaks(Array.from({ length: decoded.buffer.numberOfChannels },
        (_, i) => decoded.buffer.getChannelData(i).subarray(0, Math.ceil(duration * decoded.buffer.sampleRate)))) : [], [decoded, duration])
    const subtitle = subtitles[cue.subtitle_index]
    const visible = subtitle
        ? time >= Number(subtitle.start_num ?? subtitle.start_time) - 0.1 && time < Number(subtitle.end_num ?? subtitle.end_time)
        : offset >= -0.1 && offset < duration
    if (!visible) return null
    const active = playing && offset >= 0 && offset < duration && !!decoded && !error
    const progress = duration > 0 ? Math.max(0, Math.min(1, offset / duration)) * 640 : 0
    return <div className="mt-2 border-t border-purple-400/20 pt-2" aria-label="효과음 파형">
        <div className="flex items-center justify-between gap-2 text-[10px] text-purple-200">
            <span className="truncate" title={cue.file_name}>효과음 · {cue.file_name}</span>
            <span className="shrink-0">{error ? '재생 실패' : !decoded ? '불러오는 중' : active ? '목소리와 함께 재생 중' : offset >= duration ? '재생 완료' : '재생 대기'} · {cue.volume_db ?? -18}dB</span>
        </div>
        {error ? <p role="alert" className="text-xs text-red-300">{error}</p> : decoded ?
            <svg viewBox="0 0 640 48" preserveAspectRatio="none" className="h-10 w-full rounded bg-black/20" role="img" aria-label="효과음 실제 음파와 재생 위치">
                {displayedPeaks.map((peak, i) => <rect key={i} x={i * 640 / displayedPeaks.length} y={(48 - Math.max(1, peak * 42)) / 2}
                    width={Math.max(1, 640 / displayedPeaks.length - 1.5)} height={Math.max(1, peak * 42)} rx="0.75" fill={active ? '#c084fc' : '#6b21a8'} />)}
                <line x1={progress} x2={progress} y1="0" y2="48" stroke="#e2e8f0" strokeWidth="1.5" />
            </svg> : <div role="status" className="h-10 text-[10px] text-gray-400">효과음 파형 불러오는 중…</div>}
    </div>
}

export default function SubtitleSfxPreview({ cues, subtitles, assets, ...props }: any) {
    return <>{resolveSfxCues(cues, subtitles).map((cue, index) => <SfxTrack key={cue.id || index}
        cue={cue} subtitles={subtitles} asset={assets.find((a: any) => a.id === cue.asset_id)} {...props} />)}</>
}
