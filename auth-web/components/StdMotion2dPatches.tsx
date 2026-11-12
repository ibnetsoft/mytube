'use client'
import {useEffect, useRef, useState} from 'react'

type Patch = {id:string;role:string;sha256:string;created_at:string}
const labels:Record<string,string> = {mouth_closed:'입 닫힘',mouth_half:'입 반열림',mouth_open:'입 열림',blink:'감은 눈',hair:'머리카락'}
const button = 'rounded border border-white/20 px-3 py-2 disabled:opacity-40'

export default function StdMotion2dPatches({projectId,headers,scene,imageId,imageSha,image,backgroundAssetId,disabled}:{projectId:string;headers:Record<string,string>;scene:number;imageId:string;imageSha:string;image:string;backgroundAssetId:string;disabled:boolean}) {
    const [role,setRole]=useState('mouth_closed'),[patches,setPatches]=useState<Patch[]>([]),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[editing,setEditing]=useState(false),[brush,setBrush]=useState(14),[mode,setMode]=useState<'erase'|'restore'>('erase')
    const canvas=useRef<HTMLCanvasElement>(null),original=useRef<HTMLImageElement|null>(null),drawing=useRef(false),last=useRef<[number,number]|null>(null),undo=useRef<ImageData[]>([]),pending=useRef<string|null>(null)
    const api=`/api/std/projects/${encodeURIComponent(projectId)}/motion2d-patches`, query=`scene=${scene}&imageId=${encodeURIComponent(imageId)}&imageSha256=${encodeURIComponent(imageSha)}`
    const renderApi=`/api/std/projects/${encodeURIComponent(projectId)}/motion2d-render`
    const [job,setJob]=useState(''),[jobState,setJobState]=useState(''),[video,setVideo]=useState(''),[jobError,setJobError]=useState(''),[jobRefresh,setJobRefresh]=useState(0)
    const previousBackground=useRef(backgroundAssetId)
    useEffect(()=>{if(previousBackground.current!==backgroundAssetId){previousBackground.current=backgroundAssetId;setJob('');setVideo('');setJobState('')}},[backgroundAssetId])
    const headerKey=JSON.stringify(headers)
    useEffect(()=>{let active=true;if(!imageSha)return;void fetch(`${api}?${query}`,{headers:JSON.parse(headerKey)}).then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.error);if(active)setPatches(d.patches)}).catch(e=>{if(active)setNotice(e.message)});return()=>{active=false}},[api,query,headerKey,imageSha])
    useEffect(()=>{let active=true;void fetch(`${renderApi}?scene=${scene}`,{headers:JSON.parse(headerKey)}).then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.error);const current=d.jobs.find((j:any)=>j.image_id===imageId);if(active&&current)setJob(current.id)}).catch(e=>{if(active)setJobError(e.message)});return()=>{active=false}},[renderApi,scene,imageId,headerKey])
    useEffect(()=>{if(!job)return;let active=true,timer:ReturnType<typeof setTimeout>|undefined
        const poll=async()=>{try{const r=await fetch(`${renderApi}?scene=${scene}&id=${encodeURIComponent(job)}&backgroundId=${encodeURIComponent(backgroundAssetId)}`,{headers:JSON.parse(headerKey)}),d=await r.json();if(!r.ok)throw Error(d.error);if(!active)return;setJobState(d.state);setJobError(d.error||'');setVideo(d.url||'');if(['queued','processing'].includes(d.state))timer=setTimeout(poll,5000)}catch(e:any){if(active)setJobError(e.message)}};void poll();return()=>{active=false;if(timer)clearTimeout(timer)}
    },[renderApi,scene,job,headerKey,jobRefresh,backgroundAssetId])
    useEffect(()=>()=>{if(pending.current)URL.revokeObjectURL(pending.current)},[])
    useEffect(()=>{if(!editing||!original.current||!canvas.current)return;const c=canvas.current;c.width=original.current.naturalWidth;c.height=original.current.naturalHeight;c.getContext('2d')!.drawImage(original.current,0,0)},[editing])
    async function load(url:string) {return new Promise<HTMLImageElement>((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(Error('이미지를 읽을 수 없습니다.'));img.src=url})}
    async function begin(url:string) {
        setNotice('');setBusy(true)
        try {
            const [base,sprite]=await Promise.all([load(image),load(url)])
            if(base.naturalWidth!==sprite.naturalWidth||base.naturalHeight!==sprite.naturalHeight)throw Error('원본과 같은 크기의 투명 PNG를 선택해 주세요.')
            original.current=sprite;setEditing(true);setBusy(false)
            undo.current=[]
        } catch(e:any){setBusy(false);setNotice(e.message)}
    }
    async function openSaved(id:string) {
        setBusy(true);setNotice('')
        try {const r=await fetch(`${api}?${query}&id=${encodeURIComponent(id)}`,{headers});if(!r.ok)throw Error('패치를 불러오지 못했습니다.');const url=URL.createObjectURL(await r.blob());if(pending.current)URL.revokeObjectURL(pending.current);pending.current=url;await begin(url)}catch(e:any){setNotice(e.message);setBusy(false)}
    }
    async function beginMask(url:string) {
        setBusy(true);setNotice('')
        try {
            const [base,mask]=await Promise.all([load(image),load(url)])
            if(base.naturalWidth!==mask.naturalWidth||base.naturalHeight!==mask.naturalHeight)throw Error('마스크는 원본과 같은 크기여야 합니다.')
            const c=document.createElement('canvas');c.width=base.naturalWidth;c.height=base.naturalHeight;const ctx=c.getContext('2d')!
            ctx.drawImage(mask,0,0);const m=ctx.getImageData(0,0,c.width,c.height).data;ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(base,0,0)
            const pixels=ctx.getImageData(0,0,c.width,c.height);for(let i=0;i<m.length;i+=4)pixels.data[i+3]=Math.round((.2126*m[i]+.7152*m[i+1]+.0722*m[i+2])*m[i+3]/255);ctx.putImageData(pixels,0,0)
            const blob=await new Promise<Blob>((resolve,reject)=>c.toBlob(b=>b?resolve(b):reject(Error('마스크 변환에 실패했습니다.')),'image/png'))
            const prepared=URL.createObjectURL(blob);if(pending.current)URL.revokeObjectURL(pending.current);pending.current=prepared;await begin(prepared)
        }catch(e:any){setNotice(e.message);setBusy(false)}finally{URL.revokeObjectURL(url)}
    }
    function paint(e:React.PointerEvent<HTMLCanvasElement>) {
        const c=e.currentTarget,rect=c.getBoundingClientRect(),x=(e.clientX-rect.left)*c.width/rect.width,y=(e.clientY-rect.top)*c.height/rect.height,ctx=c.getContext('2d')!,prev=last.current || [x,y]
        ctx.save();ctx.lineWidth=brush*2;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();ctx.moveTo(prev[0],prev[1]);ctx.lineTo(x,y)
        if(mode==='erase'){ctx.globalCompositeOperation='destination-out';ctx.stroke();ctx.beginPath();ctx.arc(x,y,brush,0,Math.PI*2);ctx.fill()}
        else if(original.current){const mask=new Path2D();mask.arc(prev[0],prev[1],brush,0,Math.PI*2);mask.arc(x,y,brush,0,Math.PI*2);const dx=x-prev[0],dy=y-prev[1],len=Math.hypot(dx,dy);if(len){const nx=-dy/len*brush,ny=dx/len*brush;mask.moveTo(prev[0]+nx,prev[1]+ny);mask.lineTo(x+nx,y+ny);mask.lineTo(x-nx,y-ny);mask.lineTo(prev[0]-nx,prev[1]-ny);mask.closePath()}ctx.clip(mask);ctx.drawImage(original.current,0,0,c.width,c.height)}
        ctx.restore();last.current=[x,y]
    }
    async function save(){
        const c=canvas.current;if(!c)return
        setBusy(true);setNotice('')
        try {const blob=await new Promise<Blob>((resolve,reject)=>c.toBlob(b=>b?resolve(b):reject(Error('PNG 변환에 실패했습니다.')),'image/png'));const f=new FormData();f.set('scene',String(scene));f.set('imageId',imageId);f.set('imageSha256',imageSha);f.set('role',role);f.set('file',blob,'patch.png');const h={...headers};delete h['Content-Type'];delete h['content-type'];const r=await fetch(api,{method:'POST',headers:h,body:f}),d=await r.json();if(!r.ok)throw Error(d.error);setPatches(p=>[d.patch,...p]);setJob('');setVideo('');setJobState('');setEditing(false);setNotice('수정한 패치를 현재 씬 원본에 연결해 저장했습니다.')}catch(e:any){setNotice(e.message)}finally{setBusy(false)}
    }
    async function queue(){setBusy(true);setJobError('');setVideo('');try{const r=await fetch(renderApi,{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({scene,imageId,imageSha256:imageSha,backgroundAssetId})}),d=await r.json();if(!r.ok)throw Error(d.error);setJobState(d.state);if(d.id===job)setJobRefresh(v=>v+1);else setJob(d.id)}catch(e:any){setJobError(e.message)}finally{setBusy(false)}}
    return <section className="mt-4 rounded border border-violet-700 p-3 space-y-3" aria-label="2D 모션 패치">
        <h3 className="font-bold text-violet-200">2D 모션 얼굴·머리카락 패치</h3>
        <p className="text-xs text-gray-300">원본과 같은 크기의 투명 PNG(4MB 이하)를 올리고 외곽을 지우거나 복원합니다. 각 패치는 현재 이미지에 묶여 저장됩니다.</p>
        <p className="text-xs text-gray-300">씬마다 최신 패치 5종과 위에서 등록한 복원 배경을 사용합니다. 원본 음성의 씬 시작부터 4초를 미리보기로 만듭니다.</p>
        <label>패치 종류 <select aria-label="패치 종류" className="bg-gray-800 p-1" value={role} onChange={e=>setRole(e.target.value)} disabled={disabled||busy||editing}>{Object.entries(labels).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label>
        <label className="block">투명 PNG 불러오기 <input aria-label="2D 패치 이미지" type="file" accept="image/png" disabled={disabled||busy||editing||!imageSha} onChange={e=>{const f=e.target.files?.[0];if(f){const url=URL.createObjectURL(f);if(pending.current)URL.revokeObjectURL(pending.current);pending.current=url;void begin(url)}e.target.value=''}} /></label>
        <label className="block">흑백 마스크 후보 불러오기 <input aria-label="2D 마스크 이미지" type="file" accept="image/png" disabled={disabled||busy||editing||!imageSha} onChange={e=>{const f=e.target.files?.[0];if(f)void beginMask(URL.createObjectURL(f));e.target.value=''}} /></label>
        <div className="flex flex-wrap gap-2">{patches.filter(p=>p.role===role).slice(0,5).map((p,i)=><button className={button} disabled={disabled||busy||editing} key={p.id} onClick={()=>void openSaved(p.id)}>저장 패치 {i+1} 불러오기</button>)}</div>
        {editing && <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2"><button className={button} onClick={()=>setMode('erase')}>지우기 {mode==='erase'?'✓':''}</button><button className={button} onClick={()=>setMode('restore')}>불러온 패치 복원 {mode==='restore'?'✓':''}</button><label>브러시 <input aria-label="패치 브러시 크기" type="range" min="1" max="80" value={brush} onChange={e=>setBrush(Number(e.target.value))}/></label><button className={button} onClick={()=>{const p=undo.current.pop();if(p)canvas.current?.getContext('2d')?.putImageData(p,0,0)}}>되돌리기</button></div>
            <div className="relative w-full" style={{backgroundImage:`url(${image})`,backgroundSize:'100% 100%'}}><canvas aria-label="패치 마스크 편집" ref={canvas} className="relative" style={{display:'block',width:'100%',height:'auto',touchAction:'none'}} onPointerDown={e=>{const c=e.currentTarget;undo.current.push(c.getContext('2d')!.getImageData(0,0,c.width,c.height));if(undo.current.length>8)undo.current.shift();drawing.current=true;last.current=null;c.setPointerCapture(e.pointerId);paint(e)}} onPointerMove={e=>{if(drawing.current)paint(e)}} onPointerUp={()=>{drawing.current=false;last.current=null}} onPointerCancel={()=>{drawing.current=false;last.current=null}} /></div>
            <div className="flex gap-2"><button className={`${button} bg-violet-800`} disabled={disabled||busy} onClick={()=>void save()}>현재 패치 저장</button><button className={button} disabled={busy} onClick={()=>setEditing(false)}>편집 취소</button></div>
        </div>}
        <button className={`${button} bg-violet-800`} disabled={disabled||busy||editing||!backgroundAssetId||Object.keys(labels).some(r=>!patches.some(p=>p.role===r))} onClick={()=>void queue()}>저장 패치로 4초 미리보기 만들기</button>
        <p className="text-xs text-gray-300">{!backgroundAssetId?'먼저 위의 복원 배경을 등록해 주세요.':Object.keys(labels).some(r=>!patches.some(p=>p.role===r))?'입 3종, 눈, 머리카락 패치를 각각 저장해 주세요.':({queued:'로컬 작업 대기',processing:'로컬 작업 중',ready:'미리보기 준비됨',failed:'미리보기 실패',stale:'원본 또는 패치가 변경되어 다시 제작해야 합니다.'} as Record<string,string>)[jobState]||''}</p>
        {jobError&&<p role="alert" className="text-amber-200">{jobError}</p>}
        {video&&<video aria-label="2D 모션 4초 미리보기" src={video} controls className="w-full" />}
        <p role="status" className="text-violet-200">{notice}</p>
    </section>
}
