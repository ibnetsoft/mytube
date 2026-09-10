export const VOICE_STUDIO_PREFIX = 'gemini:'
const female = new Set('Achernar Aoede Autonoe Callirrhoe Despina Erinome Gacrux Kore Laomedeia Leda Pulcherrima Sulafat Vindemiatrix Zephyr'.split(' '))
export const VOICE_STUDIO_VOICES = 'Achernar Achird Algenib Algieba Alnilam Aoede Autonoe Callirrhoe Charon Despina Enceladus Erinome Fenrir Gacrux Iapetus Kore Laomedeia Leda Orus Puck Pulcherrima Rasalgethi Sadachbia Sadaltager Schedar Sulafat Umbriel Vindemiatrix Zephyr Zubenelgenubi'.split(' ').map(name => ({
    id: VOICE_STUDIO_PREFIX + name, name, gender: female.has(name) ? '여성' : '남성',
}))
export const isVoiceStudioVoice = (id: string) => String(id).startsWith(VOICE_STUDIO_PREFIX)
export function voiceStudioName(id: string) {
    const voice = VOICE_STUDIO_VOICES.find(v => v.id === id)
    if (!voice) throw new Error('지원하지 않는 Voice Studio 목소리입니다.')
    return voice.name
}

export function mergeVoiceStudioSegments<T extends {text:string;voiceId:string;direction?:string}>(segments:T[]):T[] {
    const result:T[]=[]
    for(const segment of segments){
        const previous=result[result.length-1]
        if(previous && isVoiceStudioVoice(segment.voiceId) && previous.voiceId===segment.voiceId
            && (previous.direction||'')===(segment.direction||'') && previous.text.length+segment.text.length+1<=1000){
            previous.text+='\n'+segment.text
        }else result.push({...segment})
    }
    return result
}
