'use client'
import { useEffect, useRef, useState } from 'react'
import { resolveSfxCues } from '@/lib/stdSfxCues'

function SfxTrack({ cue, asset, projectId, headers, time, playing, onError }: any) {
    const audioRef = useRef<HTMLAudioElement>(null)
    const [url, setUrl] = useState('')
    const headersKey = JSON.stringify(headers)
    const storageUrl = asset?.metadata?.storage_public_url || ''
    useEffect(() => {
        setUrl('')
        if (!asset?.id) return
        if (storageUrl) { setUrl(storageUrl); return }
        const controller = new AbortController()
        let objectUrl = ''
        void fetch(`/api/std/projects/${projectId}/assets/file?assetId=${encodeURIComponent(asset.id)}`, {
            headers: JSON.parse(headersKey), signal: controller.signal,
        }).then(async res => {
            if (!res.ok) throw new Error('효과음 파일을 불러오지 못했습니다.')
            const blob = await res.blob()
            if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl) }
        }).catch(error => { if (!controller.signal.aborted) onError(error.message) })
        return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
    }, [asset?.id, storageUrl, projectId, headersKey])
    useEffect(() => {
        const audio = audioRef.current
        if (!audio || !url) return
        const sync = () => {
            const offset = time - Number(cue.start || 0)
            audio.volume = Math.min(1, Math.pow(10, Number(cue.volume_db ?? -18) / 20))
            if (!playing || offset < 0 || (cue.duration && offset >= Number(cue.duration)) || (Number.isFinite(audio.duration) && offset >= audio.duration)) {
                audio.pause()
                return
            }
            if (Math.abs(audio.currentTime - offset) > 0.3) audio.currentTime = offset
            if (audio.paused) void audio.play().catch(() => onError('효과음 재생에 실패했습니다. 파일을 확인해 주세요.'))
        }
        if (audio.readyState >= 1) sync()
        else audio.addEventListener('loadedmetadata', sync, { once: true })
        return () => audio.removeEventListener('loadedmetadata', sync)
    }, [url, time, playing, cue.start, cue.volume_db, cue.duration])
    useEffect(() => () => { audioRef.current?.pause() }, [])
    return <audio ref={audioRef} src={url || undefined} preload="metadata" className="hidden" />
}

export default function SubtitleSfxPreview({ cues, subtitles, assets, ...props }: any) {
    return <>{resolveSfxCues(cues, subtitles).map((cue, index) => <SfxTrack key={cue.id || index}
        cue={cue} asset={assets.find((a: any) => a.id === cue.asset_id)} {...props} />)}</>
}
