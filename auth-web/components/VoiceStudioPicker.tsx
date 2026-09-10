'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Mic } from 'lucide-react'
import { VOICE_STUDIO_VOICES } from '@/lib/voiceStudioCatalog'

export default function VoiceStudioPicker({value, direction, onChange, headers, microphone = false, label, description}: {
    value:string; direction:string; onChange:(id:string,direction:string)=>void; headers:Record<string,string>
    microphone?:boolean; label?:string; description?:string
}) {
    const [open,setOpen]=useState(false), [search,setSearch]=useState(''), [gender,setGender]=useState('')
    const [draft,setDraft]=useState(value), [tone,setTone]=useState(direction), [busy,setBusy]=useState(''), [error,setError]=useState('')
    const player=useRef<HTMLAudioElement>(null), urls=useRef<Record<string,string>>({})
    useEffect(()=>()=>{Object.values(urls.current).forEach(URL.revokeObjectURL)},[])
    const play=async(id:string)=>{
        if(busy)return
        setBusy(id);setError('')
        try{
            if(!urls.current[id]){
                const res=await fetch('/api/std/voice-studio/sample',{method:'POST',headers,body:JSON.stringify({voice_id:id})})
                if(!res.ok){const data=await res.json();throw new Error(data.error||'샘플 생성 실패')}
                urls.current[id]=URL.createObjectURL(await res.blob())
            }
            if(player.current){player.current.src=urls.current[id];await player.current.play()}
        }catch(e:any){setError(e.message)}finally{setBusy('')}
    }
    return <>
        <button type="button" aria-label={label} title={label} onClick={(event)=>{event.stopPropagation();setDraft(value);setTone(direction);setOpen(true)}} className={microphone ? 'w-8 h-8 rounded-md border border-white/10 bg-[#10141b] text-cyan-100 flex items-center justify-center hover:border-cyan-400/50' : 'px-3 py-1.5 rounded border border-cyan-500/40 text-cyan-200 text-xs'}>{microphone ? <Mic size={14}/> : <>Voice Studio · {value.replace('gemini:','')}</>}</button>
        {open&&createPortal(<div onClick={event=>event.stopPropagation()} className="fixed inset-0 z-[100] bg-black/70 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Voice Studio 내레이션 목소리">
            <div className="bg-[#1c2027] text-gray-100 [color-scheme:dark] border border-white/20 rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col p-5 gap-3">
                <div className="flex justify-between"><h2 className="font-bold text-white">Voice Studio · 내레이션 목소리 30개</h2><button type="button" onClick={()=>{player.current?.pause();setOpen(false)}} aria-label="닫기">✕</button></div>
                <p className="text-xs text-gray-400">{description || '내레이션에만 적용합니다.'} 자막별 마이크에서는 기존 ElevenLabs 성우를 선택합니다. 샘플은 최초 생성 시 Cloud 사용료가 발생합니다.</p>
                <div className="flex gap-2"><input aria-label="목소리 검색" value={search} onChange={e=>setSearch(e.target.value)} placeholder="목소리 이름 검색" className="bg-black/30 text-gray-100 placeholder:text-gray-400 rounded p-2 flex-1"/><select aria-label="성별" value={gender} onChange={e=>setGender(e.target.value)} className="bg-[#1c2027] text-gray-100 rounded p-2"><option value="">전체</option><option>남성</option><option>여성</option></select></div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 overflow-y-auto">
                    {VOICE_STUDIO_VOICES.filter(v=>v.name.toLowerCase().includes(search.toLowerCase())&&(!gender||gender===v.gender)).map(v=><div key={v.id} className={`p-3 rounded border ${draft===v.id?'border-cyan-400 bg-cyan-900/30':'border-white/10'}`}>
                        <div className="text-sm">{v.name} · {v.gender}</div><div className="flex gap-2 mt-2 text-xs"><button type="button" disabled={!!busy} onClick={()=>void play(v.id)}>{busy===v.id?'생성 중…':'▶ 샘플 듣기'}</button><button type="button" aria-pressed={draft===v.id} onClick={()=>setDraft(v.id)}>{draft===v.id?'✓ 선택됨':'선택'}</button></div>
                    </div>)}
                </div>
                <audio ref={player} controls className="w-full h-9"/>
                {error&&<p role="alert" className="text-red-300 text-xs">{error}</p>}
                <label className="text-xs">말투·감정<input value={tone} maxLength={500} onChange={e=>setTone(e.target.value)} className="w-full bg-black/30 text-gray-100 placeholder:text-gray-400 rounded p-2 mt-1" placeholder="예: 담담하고 따뜻하게, 긴장감을 서서히 높이며"/></label>
                <button type="button" onClick={()=>{onChange(draft,tone);player.current?.pause();setOpen(false)}} className="bg-emerald-600 text-white rounded py-2 text-sm">{draft.replace('gemini:','')} 선택 완료</button>
            </div>
        </div>, document.body)}
    </>
}
