'use client'

import { useLayoutEffect, useRef, useState } from 'react'

// Keep this decision rule in sync with services/subtitle_layout.py. Measuring
// actual glyphs avoids treating narrow Latin letters like full-width CJK.
export function wrapSubtitleLines(text: string, measure: (s: string) => number, maxWidth: number): string[] {
    const output: string[] = []
    const noStart = '、。，．！？!?.,:;：；)]}）］｝」』】〉》’”ぁぃぅぇぉっゃゅょァィゥェォッャュョー'
    const noEnd = '([{（［｛「『【〈《‘“'
    const particles = 'はがをにへとものでやかのねよ은는이가을를에도의와과'
    for (const paragraph of String(text || '').replace(/\r\n?/g, '\n').split('\n')) {
        let rest = paragraph.trim()
        if (!rest) continue
        while (measure(rest) > maxWidth && Array.from(rest).length > 1) {
            const chars = Array.from(rest)
            let best: { score: number; left: string; right: string } | undefined
            for (let i = 1; i < chars.length; i++) {
                const left = chars.slice(0, i).join('').trimEnd()
                const right = chars.slice(i).join('').trimStart()
                if (!left || !right || measure(left) > maxWidth) continue
                const last = Array.from(left).at(-1) || ''
                const first = Array.from(right)[0]
                if (noStart.includes(first) || noEnd.includes(last) || /\p{Mark}/u.test(first)) continue
                const boundary = '。！？!?、，,.；;：:'.includes(last) ? 3 : /\s/u.test(chars[i - 1]) || /\s/u.test(chars[i]) ? 2 : particles.includes(last) ? 1 : 0
                const score = Math.round((measure(left) / maxWidth + boundary * 0.10 - (Array.from(right.trim()).length === 1 ? 4 : 0)) * 1000)
                if (!best || score >= best.score) best = { score, left, right }
            }
            if (!best) { output.push(chars[0]); rest = chars.slice(1).join(''); continue }
            output.push(best.left); rest = best.right
        }
        if (rest) output.push(rest)
    }
    return output.length ? output : ['']
}

type Props = { text: string; fontFamily: string; fontSize: number; color: string; strokeWidth: number; strokeColor: string; backgroundColor: string; lineSpacing: number }

export default function StdSubtitleOverlay(props: Props) {
    const box = useRef<HTMLDivElement>(null)
    const [lines, setLines] = useState<string[]>([props.text])
    useLayoutEffect(() => {
        const parent = box.current?.parentElement
        if (!parent) return
        let cancelled = false
        const update = () => {
            if (cancelled) return
            const width = parent.clientWidth
            if (!width) return
            const fontSize = width * Math.min(22, Math.max(13, props.fontSize * 2.8)) / 440
            const canvas = document.createElement('canvas')
            const context = canvas.getContext('2d')
            if (!context) return
            context.font = `400 ${fontSize}px ${JSON.stringify(props.fontFamily)}, "NotoSansJP-Bold", "NotoSansThai", sans-serif`
            setLines(wrapSubtitleLines(props.text, text => context.measureText(text).width, Math.max(1, width * 0.85 - fontSize * 1.2)))
        }
        const observer = new ResizeObserver(update)
        observer.observe(parent)
        update()
        void Promise.all([document.fonts.load(`${fontSizeForLoad(props.fontSize)}px ${JSON.stringify(props.fontFamily)}`),
            document.fonts.load('16px "NotoSansJP-Bold"'), document.fonts.load('16px "NotoSansThai"')]).then(update)
        return () => { cancelled = true; observer.disconnect() }
    }, [props.text, props.fontFamily, props.fontSize])
    return <div ref={box} className="inline-block" style={{
        fontFamily: `${JSON.stringify(props.fontFamily)}, "NotoSansJP-Bold", "NotoSansThai", sans-serif`, color: props.color,
        fontSize: `${Math.min(22, Math.max(13, props.fontSize * 2.8)) / 4.4}cqw`,
        padding: '0.3em 0.6em', borderRadius: '0.25em', fontWeight: 400,
        whiteSpace: 'pre', lineHeight: String(1 + props.lineSpacing),
        WebkitTextStroke: `${Math.max(0, props.strokeWidth) / 19.2}cqw ${props.strokeColor}`,
        paintOrder: 'stroke fill', backgroundColor: props.backgroundColor,
    }}>{lines.join('\n')}</div>
}

function fontSizeForLoad(value: number) { return Math.min(22, Math.max(13, value * 2.8)) }
