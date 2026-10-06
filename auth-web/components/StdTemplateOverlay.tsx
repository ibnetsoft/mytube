'use client'
import { useEffect, useState } from 'react'
import { drawTemplateOverlay } from '@/lib/stdTemplateOverlay'

export default function StdTemplateOverlay({ layers, savedImage, savedLayers }: { layers: any[]; savedImage?: string; savedLayers?: any[] }) {
    const signature = JSON.stringify(layers)
    const savedMatches = typeof savedImage === 'string' && savedImage.startsWith('data:image/png;base64,')
        && JSON.stringify(savedLayers) === signature
    const [image, setImage] = useState({ signature: '', url: '' })
    const [error, setError] = useState('')
    useEffect(() => {
        if (savedMatches) { setError(''); return }
        let active = true
        const target = document.createElement('canvas')
        drawTemplateOverlay(target, JSON.parse(signature)).then(() => {
            if (active) { setImage({ signature, url: target.toDataURL('image/png') }); setError('') }
        }).catch(() => { if (active) { setImage({ signature, url: '' }); setError('템플릿 미리보기를 불러오지 못했습니다.') } })
        return () => { active = false }
    }, [signature, savedMatches])
    const displayedImage = savedMatches ? savedImage : image.signature === signature ? image.url : ''
    return <>
        {displayedImage && <img src={displayedImage} alt="" data-testid="subtitle-text-template" className="absolute inset-0 z-20 w-full h-full pointer-events-none" />}
        {error && <span role="alert" className="absolute top-0 text-xs text-red-300">{error}</span>}
    </>
}
