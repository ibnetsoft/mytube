'use client'
import { useEffect, useState } from 'react'
import { wuxiaSceneFrame } from '@/lib/stdWuxiaPresentation'
import { wuxiaBubbleContour } from '@/lib/stdWuxiaBubble'

const color = (v: any, fallback: string) => Array.isArray(v) ? `rgb(${v.slice(0, 3).map((n: number) => Math.round(n * 255)).join(',')})` : fallback
function lines(text: string, width: number, size: number) {
    const count = Math.max(2, Math.floor(width / size)), result: string[] = []
    for (const paragraph of text.split('\n')) {
        let row = ''
        for (const char of Array.from(paragraph)) { if (row.length >= count) { result.push(row); row = '' }; row += char }
        result.push(row)
    }
    return result
}
export default function StdWuxiaScenePreview({ project, sceneNumber, subtitles, seconds, headers }: {
    project: any; sceneNumber: number; subtitles: any[]; seconds: number; headers: Record<string, string>
}) {
    const frame = wuxiaSceneFrame(project, sceneNumber, subtitles, seconds)
    const source = String(frame?.state?.media_url || frame?.state?.image_url || '')
    // Fetch each authored still ahead of the cut, so a slow download does not
    // leave the previous state visible over the next spoken segment.
    const sourcesKey = JSON.stringify(frame?.sources || [])
    const [images, setImages] = useState<Record<string, string>>({})
    useEffect(() => {
        const sources: string[] = JSON.parse(sourcesKey)
        let live = true
        const controller = new AbortController(), urls: string[] = []
        setImages({})
        for (const item of sources) {
            fetch(item, { headers, signal: controller.signal }).then(r => { if (!r.ok) throw Error('source unavailable'); return r.blob() })
                .then(blob => { if (live) { const url = URL.createObjectURL(blob); urls.push(url); setImages(prev => ({ ...prev, [item]: url })) } })
                .catch(() => {})
        }
        return () => { live = false; controller.abort(); urls.forEach(url => URL.revokeObjectURL(url)) }
    }, [sourcesKey, headers])
    if (!frame) return null
    return <div className="absolute inset-0 pointer-events-none" data-wuxia-presentation="authored-graphics" aria-label="무협 말풍선·타이포 미리보기">
        {images[source] && <img src={images[source]} alt="" className="absolute inset-0 h-full w-full object-cover" />}
        {(!source || images[source]) && <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1920 1080" role="img" aria-label="저장된 말풍선과 선택 타이포">
            {frame.graphics.map((g: any, i: number) => {
                const l = g.layout, speech = g.kind === 'speech_bubble'
                if (!l?.center || !l?.size) return null
                const x = l.center[0] * 1920, y = l.center[1] * 1080, w = l.size[0] * 1920, h = l.size[1] * 1080
                const rows = lines(g.text, w * (speech ? .76 : .94), g.style?.size || 38)
                const size = Math.min(g.style?.size || 38, h * .8 / (rows.length * 1.16))
                return <g key={`${g.block_id || g.kind}-${i}`}>
                    {speech && <path data-bubble-contour="unified" d={wuxiaBubbleContour([x, y], [w, h], l.tail?.map((n: number, axis: number) => n * (axis ? 1080 : 1920))).path} fill="#fffef7" stroke="#151b22" strokeWidth="3" strokeLinejoin="round" />}
                    <text x={x} y={y - (rows.length - 1) * size * .58} textAnchor="middle" dominantBaseline="central" fontFamily="Noto Sans KR, sans-serif" fontSize={size} fontWeight="bold"
                        fill={color(g.style?.fill, speech ? '#151b22' : '#fff2ca')} stroke={speech ? undefined : color(g.style?.stroke, '#15202a')} strokeWidth={speech ? 0 : g.style?.stroke_width || 2} paintOrder="stroke">
                        {rows.map((row, j) => <tspan x={x} dy={j ? size * 1.16 : 0} key={j}>{row}</tspan>)}
                    </text>
                </g>
            })}
        </svg>}
    </div>
}
