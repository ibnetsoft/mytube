'use client'
import { useEffect, useRef, useState } from 'react'
/** The editor's audio clock owns playback, pause and backward seek; footage is always muted. */
export default function StdWuxiaStateVideo({ frame, headers, active = true }: { frame:any; headers:Record<string,string>; active?:boolean }) {
    const video=useRef<HTMLVideoElement>(null), [url,setUrl]=useState(''), [error,setError]=useState('')
    const clip=frame?.clip
    useEffect(()=>{
        setUrl('');setError('');if(!clip)return
        const controller=new AbortController();let objectUrl=''
        void fetch(clip.media_url,{headers:clip.media_url.startsWith('/')?headers:undefined,signal:controller.signal})
            .then(async r=>{
                if(!r.ok)throw Error('상태 컷 영상을 불러오지 못했습니다.')
                const blob=await r.blob(),hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),n=>n.toString(16).padStart(2,'0')).join('')
                if(hash!==clip.sha256)throw Error('상태 컷 영상의 파일 지문이 다릅니다.')
                if(!controller.signal.aborted){objectUrl=URL.createObjectURL(blob);setUrl(objectUrl)}
            }).catch(e=>{if(!controller.signal.aborted)setError(e.message)})
        return()=>{controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl)}
    },[clip?.asset_id,clip?.sha256,clip?.media_url,headers])
    useEffect(()=>{const v=video.current;if(v&&url&&active&&v.readyState>=1&&Math.abs(v.currentTime-frame.source_seconds)>.01)v.currentTime=frame.source_seconds},[url,active,frame?.source_seconds])
    if(!clip)return null
    return <>
        {active&&!url&&!error&&<div role="status" className="absolute bottom-0 left-0 bg-slate-900 p-2 text-xs text-white">상태 컷 영상 로딩 중</div>}
        {url&&<video ref={video} src={url} muted playsInline preload="auto" style={{visibility:active&&!error?'visible':'hidden'}} className="absolute inset-0 h-full w-full object-cover" data-wuxia-state-video={clip.asset_id}
            onLoadedMetadata={()=>{const v=video.current!;if(v.videoWidth!==clip.width||v.videoHeight!==clip.height||Math.abs(v.duration-clip.duration_seconds)>.15)setError('영상 규격·길이가 연결 정보와 다릅니다.');else v.currentTime=frame.source_seconds}}
            onError={()=>setError('상태 컷 영상을 재생하지 못했습니다.')}/>}
        {active&&error&&<div role="alert" className="absolute bottom-0 left-0 right-0 bg-red-950 p-2 text-xs text-white">{error}</div>}
    </>
}
