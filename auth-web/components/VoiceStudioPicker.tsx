'use client'
import { useState } from 'react'
import { Mic } from 'lucide-react'
import UnifiedVoiceDialog, { type PickerVoice } from '@/components/UnifiedVoiceDialog'

export default function VoiceStudioPicker({value, direction, onChange, headers, voices = [], microphone = false, label, description, buttonText}: {
    value:string; direction:string; onChange:(id:string,direction:string)=>void | Promise<void>; headers:Record<string,string>; voices?: PickerVoice[];
    microphone?:boolean; label?:string; description?:string; buttonText?:string
}) {
    const [open, setOpen] = useState(false)
    return <>
        <button type="button" aria-label={label} title={label} onClick={(event)=>{event.stopPropagation();setOpen(true)}} className={microphone ? `${buttonText ? 'px-2.5 gap-1.5 text-[10px] font-bold' : 'w-[30px] sm:w-8'} h-[30px] sm:h-8 rounded-md border border-white/10 bg-[#10141b] text-cyan-100 flex items-center justify-center hover:border-cyan-400/50` : 'w-full max-w-full sm:w-auto sm:max-w-52 truncate px-3 py-1.5 rounded-md border border-cyan-500/40 bg-cyan-500/10 text-cyan-100 text-xs font-bold hover:bg-cyan-500/20'}>{microphone ? <><Mic size={14}/>{buttonText && <span>{buttonText}</span>}</> : <>{buttonText || value.replace('gemini:','')}</>}</button>
        {open && <UnifiedVoiceDialog value={value} direction={direction} voices={voices} initialTab="google" editDirection
            title="내레이션 성우 선택" description={description || '내레이션에만 적용합니다.'} headers={headers}
            onApply={onChange} onClose={() => setOpen(false)} />}
    </>
}
