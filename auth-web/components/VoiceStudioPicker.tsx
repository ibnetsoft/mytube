'use client'
import { useState } from 'react'
import { Mic } from 'lucide-react'
import UnifiedVoiceDialog, { type PickerVoice } from '@/components/UnifiedVoiceDialog'
import type { SupportedLocale } from '@/lib/i18n'
import { voiceDialogCopy } from '@/lib/voiceDialogLocale'

export default function VoiceStudioPicker({value, direction, onChange, headers, voices = [], historyUserId, microphone = false, label, description, buttonText, buttonClassName, locale = 'ko', scope = 'narration'}: {
    value:string; direction:string; onChange:(id:string,direction:string)=>void | Promise<void>; headers:Record<string,string>; voices?: PickerVoice[];
    locale?: SupportedLocale; scope?: 'dialogue' | 'narration';
    historyUserId?:string; microphone?:boolean; label?:string; description?:string; buttonText?:string; buttonClassName?: string
}) {
    const copy = voiceDialogCopy(locale)
    const [open, setOpen] = useState(false)
    return <>
        <button type="button" aria-label={label} title={label} onClick={(event)=>{event.stopPropagation();setOpen(true)}} className={buttonClassName || (microphone ? `${buttonText ? 'px-2.5 gap-1.5 text-[10px] font-bold' : 'w-[30px] sm:w-8'} h-[30px] sm:h-8 rounded-md border border-white/10 bg-[#10141b] text-cyan-100 flex items-center justify-center hover:border-cyan-400/50` : 'w-full max-w-full sm:w-auto sm:max-w-52 truncate px-3 py-1.5 rounded-md border border-cyan-500/40 bg-cyan-500/10 text-cyan-100 text-xs font-bold hover:bg-cyan-500/20')}>{microphone ? <><Mic size={14}/>{buttonText && <span>{buttonText}</span>}</> : <>{buttonText || value.replace('gemini:','')}</>}</button>
        {open && <UnifiedVoiceDialog locale={locale} historyUserId={historyUserId} value={value} direction={direction} voices={voices} initialTab="google" editDirection
            title={scope === 'dialogue' ? copy.dialogueTitle : copy.narrationTitle} description={description || (scope === 'dialogue' ? copy.dialogueScope : copy.narrationOnly)} headers={headers}
            onApply={onChange} onClose={() => setOpen(false)} />}
    </>
}
