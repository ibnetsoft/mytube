import { generatedSfxRows, generatedSfxForScene } from '@/lib/stdGeneratedSfxDisplay'
const seconds=(v:number)=>`${v}초`
function Cue({cue}:{cue:any}) {
    return <div data-sfx-cut={cue.cut_id} className="my-1 rounded border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100">
        <p>효과음 · {cue.cut_id} · 길이 {seconds(cue.duration_seconds)}</p>
        <p>적용 시점: 컷 시작{cue.offset_seconds ? ` 후 ${seconds(cue.offset_seconds)}` : '과 동시에'} · {cue.volume_db}dB</p>
        <p className="mt-1 whitespace-pre-wrap break-words text-gray-200">{cue.prompt}</p>
    </div>
}
export function SubtitleGeneratedSfx({project,scene,number}:{project:any;scene:any;number:number}) {
    return <>{generatedSfxForScene(project,scene,number).map((cue:any)=><Cue key={cue.id} cue={cue}/>)}</>
}
export function SubtitleGeneratedSfxList({project}:{project:any}) {
    const cues=generatedSfxRows(project)
    if(!cues.length)return null
    return <details className="mx-2 my-2 rounded border border-amber-400/30 p-2 text-xs text-amber-100" data-sfx-plan>
        <summary className="cursor-pointer">효과음 프롬프트 · {cues.length}개</summary>
        <p className="my-2 text-gray-400">저장된 생성 지침입니다. 제출 후 효과음을 생성하고 최종 컷 시간에 맞춰 배치합니다. 컷이 짧으면 끝부분을 자릅니다.</p>
        <div className="max-h-80 overflow-auto">{cues.map((cue:any)=><Cue key={cue.id} cue={cue}/>)}</div>
    </details>
}
