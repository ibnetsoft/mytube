'use client'
import StdWuxiaCinematic from './StdWuxiaCinematic'
import { useEffect, useRef, useState } from 'react'
import { mergeWuxiaMouthRefresh, preparationEnabled } from '@/lib/stdWuxiaMouthRefresh'
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
export default function StdWuxiaScenePreview({ project, sceneNumber, subtitles, seconds, headers, playing = false, audioClock }: {
    project: any; sceneNumber: number; subtitles: any[]; seconds: number; headers: Record<string, string>; playing?: boolean; audioClock?: { current: (() => number | null) | null }
}) {
    const [preciseSeconds,setPreciseSeconds]=useState<number|null>(null)
    const fps=project?.project_payload?.render_settings?.motion?.fps||24
    useEffect(()=>{
        if(!playing||!audioClock){setPreciseSeconds(null);return}
        let raf=0,lastFrame=-1
        const tick=()=>{const time=audioClock.current?.();if(time!=null){const sample=Math.floor(time*fps);if(sample!==lastFrame){lastFrame=sample;setPreciseSeconds(time)}}raf=requestAnimationFrame(tick)}
        raf=requestAnimationFrame(tick)
        return()=>cancelAnimationFrame(raf)
    },[playing,audioClock,fps])
    const [mouthUpdate,setMouthUpdate]=useState<any>(null)
    const payload=project?.project_payload||project
    const autoMouth=preparationEnabled(payload?.structure?.wuxia_mouth_policy)
    useEffect(()=>{
        if(!autoMouth||!project?.id)return
        const controller=new AbortController()
        const poll=()=>fetch(`/api/std/projects/${project.id}/wuxia-mouth`,{headers,signal:controller.signal,cache:'no-store'})
            .then(r=>r.ok?r.json():null).then(value=>{if(!controller.signal.aborted&&value?.success)setMouthUpdate(value)}).catch(()=>{})
        void poll();const timer=setInterval(poll,10000)
        return()=>{controller.abort();clearInterval(timer)}
    },[autoMouth,project?.id,headers])
    const previewSeconds=playing && preciseSeconds!==null ? preciseSeconds : seconds
    const audibleRow=playing?subtitles.find(r=>previewSeconds>=Number(r.start_num??r.start_time??r.start)&&previewSeconds<Number(r.end_num??r.end_time??r.end)):null
    const previewScene=Number(audibleRow?.scene_number)||sceneNumber
    const frame = wuxiaSceneFrame(mergeWuxiaMouthRefresh(project,mouthUpdate), previewScene, subtitles, previewSeconds)
    const source = String(frame?.state?.media_url || frame?.state?.image_url || '')
    const backdrop=String(frame?.transition.source?.media_url||frame?.transition.source?.image_url||'')
    // Fetch each authored still ahead of the cut, so a slow download does not
    // leave the previous state visible over the next spoken segment.
    const nextScene=payload?.structure?.wuxia_ae_package?.scenes?.find((s:any)=>Number(String(s.scene_id).match(/S(\d+)$/)?.[1])===previewScene+1)
    const sourcesKey = JSON.stringify([...new Set([...(frame?.sources||[]),...(nextScene?.states||[]).map((s:any)=>s.media_url||s.image_url).filter(Boolean)])])
    const [images, setImages] = useState<Record<string, string>>({})
    const imageUrls=useRef<Record<string,string>>({})
    useEffect(()=>{
        setImages({});imageUrls.current={}
        return()=>{Object.values(imageUrls.current).forEach(url=>URL.revokeObjectURL(url));imageUrls.current={}}
    },[project?.id])
    const ambientKey = JSON.stringify([...(frame?.ambientSources || []),...(frame?.mouthSources || [])])
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
        const controller = new AbortController()
        for (const item of sources) {
            if(imageUrls.current[item])continue
            fetch(item, { headers: item.startsWith('/') ? headers : undefined, signal: controller.signal }).then(r => { if (!r.ok) throw Error('source unavailable'); return r.blob() })
                .then(blob => { if (live) { const url = URL.createObjectURL(blob); imageUrls.current[item]=url; setImages(prev => ({ ...prev, [item]: url })) } })
                .catch(() => {})
        }
        return () => { live = false; controller.abort() }
    }, [sourcesKey, headers])
    if (!frame) return null
    const art=(
        <div className="absolute inset-0" data-wuxia-effect-clock="editor" data-wuxia-audio-seconds={previewSeconds} data-wuxia-effect-active={frame.effects.active.join(',')} data-wuxia-effect-issues={frame.effects.issues.join(',')} style={{transform:`translate(${frame.effects.dx/19.2}%, ${frame.effects.dy/10.8}%) scale(${frame.effects.scale})`,transformOrigin:'50% 50%'}}>
        {images[source] && <img src={images[source]} alt="" className="absolute inset-0 h-full w-full object-cover" />}
        {images[source] && frame.ambient.map(({ loop, index, frame: patch }, i) => patches[`${patch.sha256}:${loop.region.join(',')}`] &&
            <img key={i} src={patches[`${patch.sha256}:${loop.region.join(',')}`]} alt="" data-ambient-frame={index} data-ambient-clock="editor"
                className="absolute inset-0 h-full w-full object-cover" />)}
        {images[source] && frame.mouths.map(({ mouth, pose, frame: patch }:any,i:number)=>patches[`${patch.sha256}:${mouth.mouth_box.join(',')}`]&&
            <img key={`mouth-${i}`} src={patches[`${patch.sha256}:${mouth.mouth_box.join(',')}`]} alt="" data-wuxia-mouth-pose={pose} data-wuxia-mouth-speaker={mouth.speaker}
                className="absolute inset-0 h-full w-full object-cover" />)}
        {images[source] && <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1920 1080" data-wuxia-effect-overlay="protected">
            {frame.effects.overlays.map((s:any,i:number)=>s.kind==='ellipse'?<ellipse key={i} cx={s.cx} cy={s.cy} rx={s.rx} ry={s.ry} fill={s.stroke?'none':s.color} stroke={s.stroke?s.color:undefined} strokeWidth={s.stroke} opacity={s.opacity}/>:s.kind==='line'?<polyline key={i} points={s.points.map((p:number[])=>p.join(',')).join(' ')} fill="none" stroke={s.color} strokeWidth={s.width} opacity={s.opacity}/>:<polygon key={i} points={s.points.map((p:number[])=>p.join(',')).join(' ')} fill={s.color} opacity={s.opacity}/>)}
        </svg>}
        </div>
    )
    return <div className="absolute inset-0 pointer-events-none overflow-hidden bg-black" data-wuxia-presentation="authored-graphics" data-wuxia-transition={frame.transition.kind} data-wuxia-transition-issues={frame.transition.issues.join(',')} aria-label="무협 말풍선·타이포 미리보기">
        {frame.transition.backdrop>0&&images[backdrop]&&<img src={images[backdrop]} alt="" className="absolute inset-0 h-full w-full object-cover"/>}
        <div className="absolute inset-0" style={{transform:`translate(${frame.transition.dx*100}%, ${frame.transition.dy*100}%) scale(${frame.transition.scale})`,opacity:frame.transition.opacity,transformOrigin:'50% 50%'}}>
        <div className="absolute inset-0" data-wuxia-camera-clock="editor" data-wuxia-motion-issues={frame.motion.issues.join(',')} style={{transform:`translate(${frame.motion.dx*100}%, ${frame.motion.dy*100}%) scale(${frame.motion.scale})`,transformOrigin:'50% 50%'}}>
        {frame.cinematic.blur_radius>0?[0,1,2,3,4,5,6,7,8].map(i=><div key={i} className="absolute inset-0" data-wuxia-slide-blur={frame.cinematic.blur_axis} style={{opacity:1/(i+1),transform:`translate(${frame.cinematic.blur_axis==='x'?(i-4)*frame.cinematic.blur_radius/4/19.2:0}%,${frame.cinematic.blur_axis==='y'?(i-4)*frame.cinematic.blur_radius/4/10.8:0}%)`}}>{art}</div>):art}
        {frame.cinematic.blur_radius>0&&frame.cinematic.descriptor.lettering_boxes.map((b:number[],i:number)=><div key={`sharp-letter-${i}`} className="absolute inset-0" style={{clipPath:`inset(${b[1]*100}% ${(1-b[2])*100}% ${(1-b[3])*100}% ${b[0]*100}%)`}}>{art}</div>)}
        {frame.motion.heat.map((dx:number,i:number)=>dx!==0&&<div key={i} className="absolute inset-0" data-wuxia-heat-band={i} style={{clipPath:`inset(${i/frame.motion.heat.length*100}% 0 ${(1-(i+1)/frame.motion.heat.length)*100}% 0)`}}><div className="absolute inset-0" style={{transform:`translateX(${dx/19.2}%)`}}>{art}</div></div>)}
        <StdWuxiaCinematic frame={frame.cinematic}/>
        {(!source || images[source]) && <StdWuxiaGraphics graphics={frame.graphics} animate={playing} />}
        </div>
        </div>
        {frame.transition.flash>0&&<div className="absolute inset-0 bg-white" data-wuxia-transition-flash style={{opacity:frame.transition.flash}}/>}
    </div>
}
