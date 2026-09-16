'use client'

import { useEffect, useId, useState } from 'react'
import { audioWaveformPeaks, backgroundTrackPosition } from '@/lib/audioWaveform'

function clock(seconds: number) {
    const total = Math.floor(Math.max(0, seconds))
    return `${Math.floor(total / 60).toString().padStart(2, '0')}:${(total % 60).toString().padStart(2, '0')}`
}

export default function BackgroundAudioWaveform({ src, time, timelineDuration, muted }: {
    src: string; time: number; timelineDuration: number; muted: boolean
}) {
    const [wave, setWave] = useState<{ src: string; peaks: number[]; duration: number } | null>(null)
    const [error, setError] = useState('')
    const clipId = useId().replace(/:/g, '')
    useEffect(() => {
        const controller = new AbortController()
        setWave(null)
        setError('')
        if (!src) return () => controller.abort()
        void (async () => {
            try {
                const response = await fetch(src, { signal: controller.signal })
                if (!response.ok) throw new Error('audio_fetch_failed')
                const encoded = await response.arrayBuffer()
                if (controller.signal.aborted) return
                const context = new OfflineAudioContext(1, 1, 22050)
                const decoded = await context.decodeAudioData(encoded)
                if (controller.signal.aborted) return
                const channels = Array.from({ length: decoded.numberOfChannels }, (_, i) => decoded.getChannelData(i))
                setWave({ src, peaks: audioWaveformPeaks(channels), duration: decoded.duration })
            } catch {
                if (!controller.signal.aborted) setError('배경음 파형을 불러오지 못했습니다.')
            }
        })()
        return () => controller.abort()
    }, [src])

    const current = wave?.src === src ? wave : null
    const position = backgroundTrackPosition(time, current?.duration || 0)
    const progress = current?.duration ? position / current.duration * 640 : 0
    const bars = current?.peaks.map((peak, i) => {
        const height = Math.max(1, peak * 42)
        return <rect key={i} x={i * 640 / current.peaks.length} y={(48 - height) / 2}
            width={Math.max(1, 640 / current.peaks.length - 1.5)} height={height} rx="0.75" />
    })
    return <div className="mt-2 border-t border-white/10 pt-2" aria-label="배경음 파형">
        <div className="mb-1 flex items-center justify-between gap-2 text-[10px] text-cyan-200">
            <span>배경음{muted ? ' · 음소거' : ''}{current && timelineDuration > current.duration ? ' · 반복 재생' : ''}</span>
            {current && <span className="font-mono tabular-nums">{clock(position)} / {clock(current.duration)}</span>}
        </div>
        {current ? <svg viewBox="0 0 640 48" preserveAspectRatio="none" className="h-10 w-full rounded bg-black/20"
            role="img" aria-label={`배경음 길이 ${clock(current.duration)}, 현재 ${clock(position)}`}>
            <defs><clipPath id={clipId}><rect width={progress} height="48" /></clipPath></defs>
            <g fill={muted ? '#4b5563' : '#155e75'}>{bars}</g>
            <g fill={muted ? '#9ca3af' : '#22d3ee'} clipPath={`url(#${clipId})`}>{bars}</g>
            <line x1={progress} x2={progress} y1="0" y2="48" stroke="#e2e8f0" strokeWidth="1.5" />
        </svg> : <div className="flex h-10 items-center text-[10px] text-gray-400" role="status">{error || '배경음 파형 불러오는 중…'}</div>}
    </div>
}
