import {drawFinanceMotion} from './stdFinanceMotion'
import { interpolateMotion, motionKey, type MotionScene } from './stdMotionStudio'
import { applyPsdRasterMask } from './stdPsdMask'
import {renderAdvancedLayer,drawNativePaths,applyNativeEffects} from './stdWebMotionAdvanced'

export type WebLayer = { id:string; name:string; canvas:HTMLCanvasElement; left:number; top:number; opacity:number; blend:GlobalCompositeOperation }
export type WebArtwork = { width:number; height:number; layers:WebLayer[] }
export type WebShot = {videoRange?:[number,number];motionRange?:[number,number]; number:number; start:number; end:number; artwork:WebArtwork; motion:MotionScene; video?:HTMLVideoElement; originStart?:number; originEnd?:number; load?:()=>Promise<{artwork:WebArtwork;video?:HTMLVideoElement}>; dispose?:()=>void }
const outputFiles=new WeakMap<Blob,()=>Promise<void>>()
export async function releaseWebMotionFile(blob:Blob){await outputFiles.get(blob)?.();outputFiles.delete(blob)}
export type WebCaption = { start:number; end:number; text:string }
const blends:Record<string,GlobalCompositeOperation> = {normal:'source-over',multiply:'multiply',screen:'screen',overlay:'overlay',darken:'darken',lighten:'lighten','linear dodge':'lighter','soft light':'soft-light','hard light':'hard-light',difference:'difference',exclusion:'exclusion'}

/** Parse pixels in the browser. Unsupported Photoshop features fail instead of silently flattening animation. */
export async function readWebPsd(buffer:ArrayBuffer):Promise<WebArtwork> {
    if(buffer.byteLength>150*1024*1024)throw Error('PSD는 150MB 이하로 준비해 주세요.')
    const {readPsd}=await import('ag-psd')
    const header=readPsd(buffer,{skipLayerImageData:true,skipCompositeImageData:true,skipThumbnail:true})
    if(header.width*header.height>24_000_000||header.width<1||header.height<1)throw Error('PSD 캔버스는 2,400만 픽셀 이하로 준비해 주세요.')
    const psd=readPsd(buffer,{skipThumbnail:true});let layers:WebLayer[]=[]
    const maskedCanvases=new WeakMap<object,HTMLCanvasElement>()
    const visit=(items:any[],reverse:boolean,prefix='')=>{const order=items.map((item,index)=>({item,index}));if(reverse)order.reverse();order.forEach(({item,index})=>{
        if(item.hidden)return
        const id=prefix+index,opacity=item.opacity??1
        if(item.clipping||item.realMask||item.effects||item.vectorMask||item.adjustment)throw Error(`${item.name}: 클리핑·벡터 마스크·레이어 스타일은 기존 AE 방식으로 제작하거나 픽셀에 적용한 PSD로 저장해 주세요.`)
        if(item.children){
            if(item.mask&&!item.mask.disabled)throw Error(`${item.name}: 그룹 마스크는 기존 AE 방식으로 제작해 주세요.`)
            if(opacity!==1||!['normal','pass through',undefined].includes(item.blendMode))throw Error(`${item.name}: 그룹 불투명도·혼합 효과를 픽셀 레이어로 병합해 주세요.`)
            visit(item.children,reverse,id+'-');return
        }
        if(!item.canvas||!item.canvas.width||!item.canvas.height)return
        const blend=blends[item.blendMode||'normal'];if(!blend)throw Error(`${item.name}: 지원하지 않는 혼합 방식입니다.`)
        const canvas=maskedCanvases.get(item)||applyPsdRasterMask(item.canvas,item.mask,item.left||0,item.top||0)
        maskedCanvases.set(item,canvas)
        layers.push({id,name:item.name||id,canvas,left:item.left||0,top:item.top||0,opacity,blend})
    })}
    visit(psd.children||[],true)
    if(!layers.length||layers.length>80)throw Error('표시되는 픽셀 레이어 1~80개가 필요합니다.')
    if(layers.reduce((sum,l)=>sum+l.canvas.width*l.canvas.height,0)>100_000_000)throw Error('PSD 레이어 픽셀 총량이 큽니다. 사용하지 않는 레이어를 정리해 주세요.')
    if(!psd.canvas)throw Error('호환성 최대화 옵션으로 합성 이미지를 포함한 PSD를 저장해 주세요.')
    // Different PSD writers use different stack conventions. Compare both against
    // the saved original, never guess using layer names or approve missing subjects.
    const sampleScale=Math.min(160/psd.width,160/psd.height),width=Math.max(1,Math.round(psd.width*sampleScale)),height=Math.max(1,Math.round(psd.height*sampleScale)),reference=document.createElement('canvas');reference.width=width;reference.height=height
    reference.getContext('2d')!.drawImage(psd.canvas,0,0,width,height);const original=reference.getContext('2d')!.getImageData(0,0,width,height).data
    const difference=(items:WebLayer[])=>{const c=document.createElement('canvas');c.width=width;c.height=height;const ctx=c.getContext('2d')!;ctx.scale(width/psd.width,height/psd.height)
        for(const l of items){ctx.globalAlpha=l.opacity;ctx.globalCompositeOperation=l.blend;ctx.drawImage(l.canvas,l.left,l.top)}
        const pixels=ctx.getImageData(0,0,width,height).data;let sum=0;for(let i=0;i<pixels.length;i++)sum+=Math.abs(pixels[i]-original[i]);return sum/pixels.length/255
    }
    const reverseLayers=layers,reverseError=difference(layers);layers=[];visit(psd.children||[],false);const forwardError=difference(layers)
    if(Math.min(reverseError,forwardError)>.04)throw Error('PSD 레이어 합성이 저장된 원본과 다릅니다. 마스크·스타일·혼합 그룹을 픽셀 레이어에 적용해 주세요.')
    return {width:psd.width,height:psd.height,layers:reverseError<=forwardError?reverseLayers:layers}
}

export async function imageArtwork(blob:Blob):Promise<WebArtwork> {
    const bitmap=await createImageBitmap(blob)
    try {const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;canvas.getContext('2d')!.drawImage(bitmap,0,0)
        return {width:canvas.width,height:canvas.height,layers:[{id:'image',name:'원본',canvas,left:0,top:0,opacity:1,blend:'source-over'}]}
    }finally{bitmap.close()}
}

export function drawWebMotion(canvas:HTMLCanvasElement,art:WebArtwork,scene:MotionScene,time:number,caption='',overlay?:CanvasImageSource) {
    const ctx=canvas.getContext('2d')!,w=canvas.width,h=canvas.height,t=Math.max(0,Math.min(1,time)),camera=interpolateMotion(scene.keys,t)
    ctx.save();ctx.globalAlpha=1;ctx.globalCompositeOperation='source-over';ctx.fillStyle='#0c1018';ctx.fillRect(0,0,w,h)
    const fit=(scene.fit==='cover'?Math.max(w/art.width,h/art.height):Math.min(w/art.width,h/art.height))*camera.scale
    ctx.save();ctx.translate(w/2,h/2);ctx.rotate(camera.rotation*Math.PI/180);ctx.scale(fit,fit);ctx.translate(-camera.x*art.width,-camera.y*art.height)
    for(const layer of art.layers){
        const authored=scene.layers?.[layer.id],pose=authored?interpolateMotion(authored.keys,t):motionKey(t)
        const depth=authored?.depth||0,dx=(pose.x-.5)*art.width+(camera.x-.5)*art.width*depth,dy=(pose.y-.5)*art.height+(camera.y-.5)*art.height*depth
        ctx.save();ctx.globalCompositeOperation=layer.blend;ctx.globalAlpha=layer.opacity*pose.opacity/100*camera.opacity/100
        const cx=layer.left+layer.canvas.width/2,cy=layer.top+layer.canvas.height/2
        const rendered=renderAdvancedLayer(layer.canvas,authored?.advanced,t)
        ctx.translate(cx+dx,cy+dy);ctx.rotate(pose.rotation*Math.PI/180);ctx.scale(pose.scale,pose.scale);ctx.drawImage(rendered.canvas,-layer.canvas.width/2+rendered.left,-layer.canvas.height/2+rendered.top);ctx.restore()
    }
    if(scene.native?.paths.length)drawNativePaths(ctx,scene.native.paths,art.width,art.height,t)
    ctx.restore()
    if(scene.native?.effects.length){const effected=applyNativeEffects(canvas,scene.native.effects,t);ctx.clearRect(0,0,w,h);ctx.drawImage(effected,0,0)}
    if(scene.finance)drawFinanceMotion(ctx,w,h,scene.finance,t)
    for(const e of scene.effects){
        if(t<e.start||t>e.end)continue
        const u=(t-e.start)/(e.end-e.start),strength=e.intensity*Math.max(0,Math.min(1,u/.15,(1-u)/.3)),x=e.center[0]*w,y=e.center[1]*h,r=e.radius*Math.min(w,h),color=e.color.map(v=>Math.round(v*255)).join(',')
        ctx.save();ctx.strokeStyle=`rgba(${color},${strength})`;ctx.fillStyle=`rgba(${color},${strength*.65})`;ctx.lineWidth=Math.max(1,w*.003)
        switch(e.type){
            case 'impact_shake': {const copy=document.createElement('canvas');copy.width=w;copy.height=h;copy.getContext('2d')!.drawImage(canvas,0,0);ctx.drawImage(copy,-w*.015+Math.sin(u*31)*w*.005*strength,-h*.015+Math.cos(u*31)*h*.005*strength,w*1.03,h*1.03);break}
            case 'impact_flash':ctx.globalAlpha=.5;ctx.fillRect(0,0,w,h);break
            case 'shock_ring':ctx.beginPath();ctx.ellipse(x,y,r*(.1+u),r*(.1+u)*.65,0,0,Math.PI*2);ctx.stroke();break
            case 'particle_burst':case 'debris_burst':case 'warm_dust_motes':
                for(let i=0;i<24;i++){const a=i*2.399963,d=r*(.2+i%5*.15)*(e.type==='warm_dust_motes'?1:u),s=w*(e.type==='debris_burst'?.007:.003);ctx.fillRect(x+Math.cos(a)*d,y+Math.sin(a)*d-(e.type==='warm_dust_motes'?u*h*.04:0),s,s)}break
            case 'speedline_burst':for(let i=0;i<24;i++){const a=i*Math.PI/12;ctx.beginPath();ctx.moveTo(x+Math.cos(a)*r*.45,y+Math.sin(a)*r*.45);ctx.lineTo(x+Math.cos(a)*r*1.8,y+Math.sin(a)*r*1.8);ctx.stroke()}break
            case 'energy_trail':ctx.beginPath();ctx.moveTo(x-r*.8,y+r*.35);ctx.lineTo(x-r*.16,y-r*.42);ctx.lineTo(x+r*.9*u,y-r*.32);ctx.stroke();break
            default:{const cx=e.type==='light_sweep'?(.2+.6*u)*w:x,gradient=ctx.createRadialGradient(cx,y,0,cx,y,Math.max(1,r));gradient.addColorStop(0,e.type==='subtle_vignette'?'transparent':`rgba(${color},${strength*.45})`);gradient.addColorStop(1,e.type==='subtle_vignette'?`rgba(0,0,0,${strength*.5})`:'transparent');ctx.fillStyle=gradient;ctx.fillRect(0,0,w,h)}
        }
        ctx.restore()
    }
    if(t<.08&&scene.transition!=='cut'){ctx.fillStyle=scene.transition==='flash'?'white':'black';ctx.globalAlpha=1-t/.08;ctx.fillRect(0,0,w,h);ctx.globalAlpha=1}
    if(overlay)ctx.drawImage(overlay,0,0,w,h)
    if(caption){
        const size=Math.round(Math.min(w*.045,h*.055));ctx.font=`600 ${size}px sans-serif`;ctx.textAlign='center';ctx.lineJoin='round';ctx.lineWidth=size*.16;ctx.strokeStyle='black';ctx.fillStyle='white'
        const lines:string[]=[];let line='';for(const char of caption){if(char==='\n'||ctx.measureText(line+char).width>w*.88){lines.push(line);line=char==='\n'?'':char}else line+=char}if(line)lines.push(line)
        lines.forEach((text,i)=>{const y=h*.91-(lines.length-1-i)*size*1.3;ctx.strokeText(text,w/2,y);ctx.fillText(text,w/2,y)})
    }
    ctx.restore()
}

export async function uploadWebMotion(projectId:string,headers:Record<string,string>,file:File,type:'original'|'video'|'image',scene:number|null) {
    const base=`/api/std/projects/${projectId}/assets`,payload={asset_type:type,scene_number:scene,file_name:file.name,mime_type:file.type||'image/vnd.adobe.photoshop'}
    const start=await fetch(base+'/init',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify(payload)}),init=await start.json()
    if(!start.ok)throw Error(init.error)
    const put=await fetch(init.storage_upload_url,{method:'PUT',headers:{'Content-Type':payload.mime_type},body:file});if(!put.ok)throw Error('원본 업로드에 실패했습니다.')
    const finish=await fetch(base+'/complete',{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({...init,...payload,file_size:file.size})}),result=await finish.json()
    if(!finish.ok)throw Error(result.error)
    return result.asset
}

/** Offline frame timestamps; never records the screen, microphone, or wall-clock animation. */
export async function exportWebMotion(shots:WebShot[],voice:AudioBuffer,captions:WebCaption[],aspect:'16:9'|'9:16',fps:24|30,signal:AbortSignal,progress:(n:number)=>void,overlay?:CanvasImageSource) {
    const {Output,Mp4OutputFormat,BufferTarget,StreamTarget,CanvasSource,AudioBufferSource,canEncodeVideo,canEncodeAudio}=await import('mediabunny')
    if(!await canEncodeVideo('avc')||!await canEncodeAudio('aac'))throw Error('이 브라우저는 MP4 인코딩을 지원하지 않습니다. 최신 Chrome 또는 Edge에서 열어 주세요.')
    if(!shots.length||shots[0].start!==0||shots.some((s,i)=>!Number.isFinite(s.end)||s.end<=s.start||(i>0&&Math.abs(s.start-shots[i-1].end)>.001)))throw Error('음성에 맞춘 연속 장면 구간이 필요합니다.')
    const duration=shots.at(-1)!.end
    if(Math.abs(voice.duration-duration)>.15)throw Error('최종 음성과 장면 길이가 일치하지 않습니다.')
    const canvas=document.createElement('canvas');canvas.width=aspect==='9:16'?1080:1920;canvas.height=aspect==='9:16'?1920:1080
    let file:FileSystemFileHandle|undefined,remove:(()=>Promise<void>)|undefined,writable:FileSystemWritableFileStream|undefined
    if(navigator.storage?.getDirectory){
        const root=await navigator.storage.getDirectory(),directory=await root.getDirectoryHandle('air-motion-temp',{create:true}),name=`motion-export-${crypto.randomUUID()}.mp4`
        // A closed/crashed tab cannot run React cleanup. Reap old temporary exports
        // on the next session without touching other browser storage.
        for await(const handle of (directory as any).values())if(handle.kind==='file'&&handle.name.startsWith('motion-export-')){const old=await handle.getFile();if(Date.now()-old.lastModified>24*60*60*1000)await directory.removeEntry(handle.name).catch(()=>{})}
        file=await directory.getFileHandle(name,{create:true});remove=()=>directory.removeEntry(name);writable=await file.createWritable()
    }else if(duration>120)throw Error('긴 영상 제작에는 브라우저 파일 저장소를 지원하는 최신 Chrome 또는 Edge가 필요합니다.')
    const target=writable?new StreamTarget(writable,{chunked:true,chunkSize:4*1024*1024}):new BufferTarget()
    const output=new Output({format:new Mp4OutputFormat({fastStart:writable?'fragmented':'in-memory'}),target}),video=new CanvasSource(canvas,{codec:'avc',bitrate:8_000_000}),audio=new AudioBufferSource({codec:'aac',bitrate:192_000})
    output.addVideoTrack(video,{frameRate:fps});output.addAudioTrack(audio)
    let audioFailure:unknown=null,active:WebShot|undefined
    try{
        await output.start()
        const audioDone=audio.add(voice).then(()=>audio.close()).catch(e=>{audioFailure=e})
        let index=0
        for(let frame=0;frame<Math.ceil(duration*fps);frame++){
            signal.throwIfAborted();if(audioFailure)throw audioFailure
            const t=frame/fps;while(index<shots.length-1&&t>=shots[index].end)index++
            const shot=shots[index]
            if(shot!==active){if(active){active.dispose?.();if(active.load){active.artwork={width:0,height:0,layers:[]};active.video=undefined}}active=shot;if(shot.load)Object.assign(shot,await shot.load())}
            if(shot.video){const v=shot.video,target=Math.min(shot.videoRange?shot.videoRange[0]+(shot.videoRange[1]-shot.videoRange[0])*(t-shot.start)/(shot.end-shot.start):shot.motionRange?(shot.motionRange[0]+(shot.motionRange[1]-shot.motionRange[0])*(t-shot.start)/(shot.end-shot.start))*v.duration:t-(shot.originStart??shot.start),Math.max(0,v.duration-1/fps));if(Math.abs(v.currentTime-target)>.0001)await new Promise<void>((resolve,reject)=>{const timeout=setTimeout(()=>{cleanup();reject(Error('영상 프레임 읽기 시간 초과'))},15000);const cleanup=()=>{clearTimeout(timeout);v.removeEventListener('seeked',done);v.removeEventListener('error',fail)};const done=()=>{cleanup();resolve()},fail=()=>{cleanup();reject(Error('영상 프레임 읽기 실패'))};v.addEventListener('seeked',done,{once:true});v.addEventListener('error',fail,{once:true});v.currentTime=target});shot.artwork.layers[0].canvas.getContext('2d')!.drawImage(v,0,0)}
            drawWebMotion(canvas,shot.artwork,shot.motion,shot.motionRange?shot.motionRange[0]+(shot.motionRange[1]-shot.motionRange[0])*(t-shot.start)/(shot.end-shot.start):(t-(shot.originStart??shot.start))/((shot.originEnd??shot.end)-(shot.originStart??shot.start)),captions.filter(c=>t>=c.start&&t<c.end).map(c=>c.text).join('\n'),overlay)
            await video.add(t,Math.min(1/fps,duration-t));if(frame%fps===0){progress(frame/(duration*fps)*100);await new Promise(r=>setTimeout(r,0))}
        }
        video.close();await audioDone;if(audioFailure)throw audioFailure;await output.finalize();progress(100)
        const blob=file?new File([await file.getFile()],'motion-studio-final.mp4',{type:'video/mp4'}):new Blob([(target as InstanceType<typeof BufferTarget>).buffer!],{type:'video/mp4'})
        if(remove)outputFiles.set(blob,remove)
        return blob
    }catch(e){try{await output.cancel()}finally{await remove?.().catch(()=>{})}throw e}
    finally{active?.dispose?.();if(active?.load){active.artwork={width:0,height:0,layers:[]};active.video=undefined}}
}

export async function mixWebMotionAudio(voice:AudioBuffer,tracks:{buffer:AudioBuffer;start:number;end:number;volume:number;loop:boolean;fadeIn:number;fadeOut:number}[]) {
    if(!tracks.length)return voice
    const context=new OfflineAudioContext(2,voice.length,voice.sampleRate),narration=context.createBufferSource();narration.buffer=voice;narration.connect(context.destination);narration.start(0)
    for(const track of tracks){
        const end=Math.min(voice.duration,track.end,track.loop?Infinity:track.start+track.buffer.duration),start=Math.max(0,track.start)
        if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)throw Error('배경음·효과음 구간을 확인해 주세요.')
        const node=context.createBufferSource(),gain=context.createGain();node.buffer=track.buffer;node.loop=track.loop
        const volume=Math.max(0,Math.min(1,track.volume)),fadeIn=Math.min(track.fadeIn,(end-start)/2),fadeOut=Math.min(track.fadeOut,(end-start)/2)
        gain.gain.setValueAtTime(fadeIn>0?0:volume,start);if(fadeIn>0)gain.gain.linearRampToValueAtTime(volume,start+fadeIn)
        if(fadeOut>0){gain.gain.setValueAtTime(volume,end-fadeOut);gain.gain.linearRampToValueAtTime(0,end)}
        node.connect(gain);gain.connect(context.destination);node.start(start);node.stop(end)
    }
    return context.startRendering()
}
