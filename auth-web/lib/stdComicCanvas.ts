import { COMIC_LAYOUTS, ComicSettings } from './stdComic'

export type ComicMedia = HTMLImageElement | HTMLVideoElement
const W = 1280, H = 720
export function drawComicPage(canvas: HTMLCanvasElement, scenes: any[], media: ComicMedia[], settings: ComicSettings,
    timings: ReturnType<typeof import('./stdComic').comicSceneTimings>, sourceTime: number, allBalloons = false) {
    canvas.width = W; canvas.height = H
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#f7f2e8'; ctx.fillRect(0, 0, W, H)
    if (settings.layout === 'spread') {
        ctx.strokeStyle = '#c8bfae'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(W / 2, H * .02); ctx.lineTo(W / 2, H * .98); ctx.stroke()
    }
    scenes.forEach((scene, slot) => {
        const [nx, ny, nw, nh] = COMIC_LAYOUTS[settings.layout][slot]
        const x = Math.round(nx * W), y = Math.round(ny * H), w = Math.round(nw * W), h = Math.round(nh * H)
        const item = media[slot], timing = timings[slot]
        const options = settings.panels[String(scene.scene_number)] || {}
        ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip()
        ctx.fillStyle = '#ebe5d9'; ctx.fillRect(x, y, w, h)
        if (item) {
            const mw = item instanceof HTMLVideoElement ? item.videoWidth : item.naturalWidth
            const mh = item instanceof HTMLVideoElement ? item.videoHeight : item.naturalHeight
            if (mw && mh) {
                const scale = options.fit === 'cover' ? Math.max(w / mw, h / mh) : Math.min(w / mw, h / mh)
                ctx.drawImage(item, x + (w - mw * scale) / 2, y + (h - mh * scale) / 2, mw * scale, mh * scale)
            }
        }
        if (settings.dim_inactive && !allBalloons && !(sourceTime >= timing.start && sourceTime < timing.end)) {
            ctx.fillStyle = 'rgba(0,0,0,.22)'; ctx.fillRect(x, y, w, h)
        }
        const blocks = timing.blocks
        const pad = Math.max(5, Math.round(w * .025)), bw = w - pad * 4
        let fontSize = Math.min(settings.font_size, Math.max(12, Math.floor(w / 12)))
        let lines: string[][] = [], heights: number[] = [], total = 0, lineH = 0
        while (true) {
            ctx.font = `${fontSize}px ComicBalloon, sans-serif`
            lineH = Math.ceil(fontSize * 1.3)
            lines = blocks.map(block => String(block.text || '').split('\n').flatMap(paragraph => {
                const result: string[] = []; let line = ''
                for (const char of paragraph) {
                    if (line && ctx.measureText(line + char).width > bw - pad * 2) { result.push(line); line = char }
                    else line += char
                }
                result.push(line); return result
            }))
            heights = lines.map(ls => Math.max(lineH, ls.length * lineH) + pad * 2)
            total = heights.reduce((a, b) => a + b, 0) + Math.max(0, blocks.length - 1) * pad * 2
            if (total <= h * .84 || !blocks.length) break
            if (fontSize <= 12) throw new Error(`씬 ${scene.scene_number}: 말풍선이 컷을 넘칩니다. 대사를 줄이거나 전체 1컷을 선택하세요.`)
            fontSize--
        }
        let by = options.bubble_position === 'top' ? y + pad * 2 : y + h - total - pad * 2
        blocks.forEach((block, i) => {
            if (allBalloons || sourceTime >= Number(block.start_time ?? block.start ?? 0)) {
                const bx = x + pad * 2, bh = heights[i]
                ctx.fillStyle = '#fff'; ctx.strokeStyle = '#252525'; ctx.lineWidth = Math.max(1, Math.floor(pad / 3))
                ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, pad * 2); ctx.fill(); ctx.stroke()
                ctx.beginPath(); ctx.moveTo(bx + pad * 3, by + bh - 2); ctx.lineTo(bx + pad * 3, by + bh + pad); ctx.lineTo(bx + pad * 5, by + bh - 2); ctx.fill(); ctx.stroke()
                ctx.fillStyle = '#171717'; ctx.textBaseline = 'top'
                lines[i].forEach((line, n) => ctx.fillText(line, bx + pad, by + pad + n * lineH))
            }
            by += heights[i] + pad * 2
        })
        ctx.restore(); ctx.strokeStyle = '#222'; ctx.lineWidth = 2; ctx.strokeRect(x, y, w, h)
    })
}
