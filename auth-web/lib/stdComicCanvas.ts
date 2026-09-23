import { drawLettering } from './stdComicLettering'
import { COMIC_LAYOUTS, ComicSettings } from './stdComic'

export type ComicMedia = HTMLImageElement | HTMLVideoElement
const W = 1280, H = 720
export function drawComicPage(canvas: HTMLCanvasElement, scenes: any[], media: ComicMedia[], settings: ComicSettings,
    timings: ReturnType<typeof import('./stdComic').comicSceneTimings>, sourceTime: number, allBalloons = false, pageIndex = 0) {
    canvas.width = W; canvas.height = H
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#f7f2e8'; ctx.fillRect(0, 0, W, H)
    const layoutName=settings.page_layouts?.[String(pageIndex)] || settings.layout
    if (['spread','double'].includes(layoutName)) {
        ctx.strokeStyle = '#c8bfae'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(W / 2, H * .02); ctx.lineTo(W / 2, H * .98); ctx.stroke()
    }
    scenes.forEach((scene, slot) => {
        const [nx, ny, nw, nh] = COMIC_LAYOUTS[layoutName][slot]
        const x = Math.round(nx * W), y = Math.round(ny * H), w = Math.round(nw * W), h = Math.round(nh * H)
        const item = media[slot], timing = timings[slot]
        const options = settings.panels[String(scene.scene_number)] || {}
        ctx.save(); ctx.beginPath()
        if(layoutName==='diagonal') {if(slot===0){ctx.moveTo(x,y);ctx.lineTo(x+w,y);ctx.lineTo(x,y+h)}else{ctx.moveTo(x+w,y+5);ctx.lineTo(x+w,y+h);ctx.lineTo(x+5,y+h)}ctx.closePath()}else ctx.rect(x,y,w,h)
        ctx.clip()
        if(!(layoutName==='breakout'&&slot===1)){ctx.fillStyle = '#ebe5d9'; ctx.fillRect(x, y, w, h)}
        if (item) {
            const mw = item instanceof HTMLVideoElement ? item.videoWidth : item.naturalWidth
            const mh = item instanceof HTMLVideoElement ? item.videoHeight : item.naturalHeight
            if (mw && mh) {
                let scale = options.fit === 'cover' ? Math.max(w / mw, h / mh) : Math.min(w / mw, h / mh)
                if(options.motion==='pan' && !(item instanceof HTMLVideoElement)) scale*=1+.07*Math.max(0,Math.min(1,(sourceTime-timing.start)/timing.duration))
                ctx.drawImage(item, x + (w - mw * scale) / 2, y + (h - mh * scale) / 2, mw * scale, mh * scale)
            }
        }
        if (settings.dim_inactive && !allBalloons && !(sourceTime >= timing.start && sourceTime < timing.end)) {
            ctx.fillStyle = 'rgba(0,0,0,.22)'; ctx.fillRect(x, y, w, h)
        }
        const blocks = timing.blocks.map((b:any,j:number)=>({...b,comic:settings.lettering?.[`${scene.scene_number}:${j}`] || b.comic || (layoutName==='diagonal'?{x:slot===0?.05:.55,y:slot===0?.05:.68,width:.4}: {})}))
        ctx.translate(x,y)
        drawLettering(ctx,w,h,blocks,settings.font_size,options.bubble_position || 'bottom',sourceTime,allBalloons,layoutName==='diagonal'?slot:undefined)
        ctx.restore(); ctx.strokeStyle = '#222'; ctx.lineWidth = 2
        if(layoutName==='diagonal'){ctx.beginPath();ctx.moveTo(x+w,y);ctx.lineTo(x,y+h);ctx.stroke()}
        else if(!['borderless','bleed','double'].includes(layoutName) && !(layoutName==='breakout'&&slot===1))ctx.strokeRect(x, y, w, h)
    })
}
