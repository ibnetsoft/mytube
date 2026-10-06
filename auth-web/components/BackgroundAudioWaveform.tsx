'use client'

import { stdUiText } from '@/lib/stdUiText'
import type { SupportedLocale } from '@/lib/i18n'

import { useEffect, useId, useState } from 'react'
import { audioWaveformPeaks, backgroundTrackPosition } from '@/lib/audioWaveform'
import { backgroundPlaybackWindow, backgroundWaveformPeaks } from '@/lib/stdAudioMix'

function clock(seconds: number) {
    const total = Math.floor(Math.max(0, seconds))
    return `${Math.floor(total / 60).toString().padStart(2, '0')}:${(total % 60).toString().padStart(2, '0')}`
}

function preciseClock(seconds: number) {
    const tenths = Math.round(Math.max(0, seconds) * 10)
    return `${Math.floor(tenths / 600).toString().padStart(2, '0')}:${(Math.floor(tenths / 10) % 60).toString().padStart(2, '0')}.${tenths % 10}`
}

export default function BackgroundAudioWaveform({ locale = 'ko', src, time, timelineDuration, muted, loop = true, startTime = 0, fadeIn = 0, fadeOut = 0 }: {
    locale?: SupportedLocale; src: string; time: number; timelineDuration: number; muted: boolean; loop?: boolean; startTime?: number; fadeIn?: number; fadeOut?: number
}) {
    const ui = (text: string) => stdUiText(locale, text)
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
    const position = backgroundTrackPosition(time, current?.duration || 0, loop)
    const progress = current?.duration ? position / current.duration * 640 : 0
    const window = { start: startTime, end: startTime + timelineDuration, valid: timelineDuration > 0, fadeIn, fadeOut }
    const range = backgroundPlaybackWindow(window, current?.duration || 0, loop)
    const peaks = current ? backgroundWaveformPeaks(current.peaks, current.duration, window, startTime + time, loop) : []
    const bars = peaks.map((peak, i) => {
        const height = Math.max(1, peak * 42)
        return <rect key={i} x={i * 640 / peaks.length} y={(48 - height) / 2}
            width={Math.max(1, 640 / peaks.length - 1.5)} height={height} rx="0.75" />
    })
    return <div className="mt-2 border-t border-white/10 pt-2" aria-label={ui("배경음 파형")}>
        <div className="mb-1 flex items-center justify-between gap-2 text-[10px] text-cyan-200">
            <span>{ui("배경음")}{muted ? ` · ${ui("음소거")}` : ''}{loop && current && timelineDuration > current.duration ? ` · ${ui("반복 재생")}` : !loop ? ` · ${ui("한 번 재생")}` : ''}</span>
            {current && <span className="font-mono tabular-nums">{clock(position)} / {clock(current.duration)}</span>}
        </div>
        {current ? <svg viewBox="0 0 640 48" preserveAspectRatio="none" className="h-10 w-full rounded bg-black/20"
            role="img" aria-label={`${ui("배경음 길이")} ${clock(current.duration)}, ${ui("현재")} ${clock(position)}`}>
            <defs><clipPath id={clipId}><rect width={progress} height="48" /></clipPath></defs>
            <g fill={muted ? '#4b5563' : '#155e75'}>{bars}</g>
            <g fill={muted ? '#9ca3af' : '#22d3ee'} clipPath={`url(#${clipId})`}>{bars}</g>
            <line x1={progress} x2={progress} y1="0" y2="48" stroke="#e2e8f0" strokeWidth="1.5" />
        </svg> : <div className="flex h-10 items-center text-[10px] text-gray-400" role="status">{ui(error || "배경음 파형 불러오는 중…")}</div>}
        {current && range.valid && range.fadeOut > 0 && <p className="mt-1 text-[10px] tabular-nums text-cyan-200" aria-label={ui('페이드 아웃 구간')}>
            {ui('페이드 아웃')} · {preciseClock(range.end - range.fadeOut)} → {preciseClock(range.end)} ({range.fadeOut.toFixed(1)}{ui('초')})
        </p>}
    </div>
}
