'use client'
import { useEffect, useState } from 'react'
import { wuxiaSceneFrame } from '@/lib/stdWuxiaPresentation'
import { wuxiaBubbleContour } from '@/lib/stdWuxiaBubble'

import { wuxiaFontFamily, wuxiaTextLines, wuxiaGraphicPose } from '@/lib/stdWuxiaGraphic'

const color = (v: any, fallback: string) => Array.isArray(v) ? `rgb(${v.slice(0, 3).map((n: number) => Math.round(n * 255)).join(',')})` : fallback
export function StdWuxiaGraphics({ graphics, animate = true }: { graphics: any[]; animate?: boolean }) {
 return <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1920 1080" role="img" aria-label="저장된 말풍선과 선택 타이포">
  {graphics.map((g: any, i: number) => {
   const l=g.layout,s=g.style||{},speech=g.kind==='speech_bubble'
   if(!l?.center||!l?.size)return null
   const x=l.center[0]*1920,y=l.center[1]*1080,w=l.size[0]*1920,h=l.size[1]*1080
   const rows=wuxiaTextLines(g.text,w*(speech?.72:.94),s.size||38)
   const size=Math.min(s.size||38,h*.76/(rows.length*1.16)),pose=wuxiaGraphicPose(g,animate?(g.progress??.5):.5)
   return <g key={`${g.block_id||g.kind}-${i}`} data-graphic-kind={g.kind} data-bubble-style={speech?(g.bubble_style||'dialogue'):undefined} opacity={pose.opacity}
    transform={`translate(${x} ${y}) rotate(${pose.rotation}) scale(${pose.scale}) translate(${-x} ${-y})`}>
    {speech&&<path data-bubble-contour="unified" d={wuxiaBubbleContour([x,y],[w,h],l.offscreen_speaker?undefined:l.tail?.map((n:number,axis:number)=>n*(axis?1080:1920)),g.bubble_style).path}
     fill="#fffef7" stroke="#151b22" strokeWidth="3" strokeLinejoin="round" strokeDasharray={g.bubble_style==='whisper'?'12 8':undefined}/>}
    <text x={x} y={y-(rows.length-1)*size*.58} textAnchor="middle" dominantBaseline="central" fontFamily={wuxiaFontFamily(s.font)} fontSize={size} fontWeight="bold"
     fill={color(s.fill,speech?'#151b22':'#fff2ca')} stroke={speech?undefined:color(s.stroke,'#15202a')} strokeWidth={speech?0:s.stroke_width||2} paintOrder="stroke">
     {rows.map((row,j)=><tspan x={x} dy={j?size*1.16:0} key={j}>{row}</tspan>)}
    </text>
   </g>
  })}
 </svg>
}
export default function StdWuxiaScenePreview({ project, sceneNumber, subtitles, seconds, headers, playing = false }: {
    project: any; sceneNumber: number; subtitles: any[]; seconds: number; headers: Record<string, string>; playing?: boolean
}) {
    const frame = wuxiaSceneFrame(project, sceneNumber, subtitles, seconds)
    const source = String(frame?.state?.media_url || frame?.state?.image_url || '')
    // Fetch each authored still ahead of the cut, so a slow download does not
    // leave the previous state visible over the next spoken segment.
    const sourcesKey = JSON.stringify(frame?.sources || [])
    const [images, setImages] = useState<Record<string, string>>({})
    const ambientKey = JSON.stringify(frame?.ambientSources || [])
    const [patches, setPatches] = useState<Record<string, string>>({})
    useEffect(() => {
        const sources = JSON.parse(ambientKey) as { media_url: string; sha256: string; region: number[]; width: number; height: number }[]
        const controller = new AbortController(), urls: string[] = []
        let live = true
        setPatches({})
        // Authenticate only same-origin media; never send the session token to GCS.
        const queue=[...new Map(sources.map(item=>[`${item.sha256}:${item.region.join(',')}`,item])).values()]
        const consume=async()=>{while(live&&queue.length){
            const item=queue.shift()!
            await fetch(item.media_url, { headers: item.media_url.startsWith('/') ? headers : undefined, signal: controller.signal })
                .then(async r => {
                    if (!r.ok) throw Error('ambient frame unavailable')
                    const blob = await r.blob(), data = await blob.arrayBuffer()
                    const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)), n => n.toString(16).padStart(2, '0')).join('')
                    if (hash !== item.sha256 || blob.type !== 'image/png') throw Error('ambient frame identity mismatch')
                    const bitmap=await createImageBitmap(blob)
                    if(bitmap.width!==item.width||bitmap.height!==item.height){bitmap.close();throw Error('ambient canvas mismatch')}
                    // Enforce the approved envelope in preview as well as on the worker.
                    const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height
                    const context=canvas.getContext('2d');if(!context){bitmap.close();throw Error('ambient canvas unavailable')}
                    const [left,top,right,bottom]=item.region,x=Math.ceil(left*bitmap.width),y=Math.ceil(top*bitmap.height),w=Math.floor(right*bitmap.width)-x,h=Math.floor(bottom*bitmap.height)-y
                    context.drawImage(bitmap,x,y,w,h,x,y,w,h);bitmap.close()
                    const clipped=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(Error('ambient frame unavailable')),'image/png'))
                    canvas.width=0;canvas.height=0
                    if (live) { const url=URL.createObjectURL(clipped); urls.push(url); setPatches(prev=>({...prev,[`${item.sha256}:${item.region.join(',')}`]:url})) }
                }).catch(()=>{}) // Preserve the authoritative still on failure.
        }}
        for(let i=0;i<Math.min(4,queue.length);i++)void consume()
        return () => { live=false; controller.abort(); urls.forEach(url=>URL.revokeObjectURL(url)) }
    }, [ambientKey, headers])
    useEffect(() => {
        const sources: string[] = JSON.parse(sourcesKey)
        let live = true
        const controller = new AbortController(), urls: string[] = []
        setImages({})
        for (const item of sources) {
            fetch(item, { headers: item.startsWith('/') ? headers : undefined, signal: controller.signal }).then(r => { if (!r.ok) throw Error('source unavailable'); return r.blob() })
                .then(blob => { if (live) { const url = URL.createObjectURL(blob); urls.push(url); setImages(prev => ({ ...prev, [item]: url })) } })
                .catch(() => {})
        }
        return () => { live = false; controller.abort(); urls.forEach(url => URL.revokeObjectURL(url)) }
    }, [sourcesKey, headers])
    if (!frame) return null
    return <div className="absolute inset-0 pointer-events-none" data-wuxia-presentation="authored-graphics" aria-label="무협 말풍선·타이포 미리보기">
        {images[source] && <img src={images[source]} alt="" className="absolute inset-0 h-full w-full object-cover" />}
        {images[source] && frame.ambient.map(({ loop, index, frame: patch }, i) => patches[`${patch.sha256}:${loop.region.join(',')}`] &&
            <img key={i} src={patches[`${patch.sha256}:${loop.region.join(',')}`]} alt="" data-ambient-frame={index} data-ambient-clock="editor"
                className="absolute inset-0 h-full w-full object-cover" />)}
        {(!source || images[source]) && <StdWuxiaGraphics graphics={frame.graphics} animate={playing} />}
    </div>
}
