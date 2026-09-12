'use client'
import { useEffect, useRef, useState } from 'react'
import { drawThumbnail, loadThumbnailBackground, ThumbnailLayer } from '@/lib/stdThumbnailRender'

export default function StdThumbnailPreview({ background, layers, headers }: {
    background: string; layers: ThumbnailLayer[]; headers?: HeadersInit
}) {
    const canvas = useRef<HTMLCanvasElement>(null)
    const [image, setImage] = useState<HTMLImageElement | null>(null)
    const [error, setError] = useState('')
    const headerKey = JSON.stringify(headers || {})
    const revision = useRef(0)
    useEffect(() => {
        let active = true
        setImage(null); setError('')
        if (canvas.current) canvas.current.getContext('2d')?.clearRect(0, 0, 1280, 720)
        if (background) loadThumbnailBackground(background, headers).then(value => {
            if (active) setImage(value)
        }).catch(e => { if (active) setError(e.message) })
        return () => { active = false }
    }, [background, headerKey])
    useEffect(() => {
        const current = ++revision.current
        if (!image || !canvas.current) return
        // Render offscreen so slower font loads cannot overwrite newer edits.
        const offscreen = document.createElement('canvas')
        drawThumbnail(offscreen, image, layers).then(() => {
            if (current === revision.current && canvas.current) {
                canvas.current.width = 1280; canvas.current.height = 720
                canvas.current.getContext('2d')?.drawImage(offscreen, 0, 0)
            }
        }).catch(e => { if (current === revision.current) setError(e.message) })
        return () => { ++revision.current }
    }, [image, layers])
    return <div className="relative aspect-video bg-black overflow-hidden select-none">
        <canvas ref={canvas} width={1280} height={720} className="w-full h-full" aria-label="편집 가능한 썸네일 합성 미리보기" />
        {(!background || error) && <p className="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-gray-300">
            {error || '글자 없는 배경 이미지를 생성하거나 업로드해 주세요.'}
        </p>}
    </div>
}
