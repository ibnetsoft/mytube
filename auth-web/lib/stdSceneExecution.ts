import { createHash } from 'crypto'
/** Compile only new direction contracts; persisted v1 projects keep their settings. */
export const SCENE_DIRECTION_CONTRACT = 'scene_direction_plan/v2'
export function directedScene(direction: any) { return direction?.contract === SCENE_DIRECTION_CONTRACT }

export function bindSceneDirection(direction: any, source: string, rows: any[], start: number, end: number, fps: number) {
    if (!directedScene(direction)) return null
    const design = direction.execution_design, camera = design?.camera
    if (design?.graphics?.speech_bubbles || design?.graphics?.speedlines) throw new Error('말풍선·속도선은 실제 화자 위치와 효과 구간을 검수한 AE 그래픽 계획이 필요합니다. 일반 카메라 경로로 대체하지 않습니다.')
    if (!camera || !Array.isArray(camera.keys) || camera.keys.length < 2 || camera.keys.length > 8) throw new Error('장면별 카메라 경로를 다시 준비해 주세요.')
    const quoteWindow = (quote: string) => {
        const text = rows.map(r => String(r.text || '')).join('')
        const at = text.indexOf(quote)
        if (!quote.trim() || at < 0 || text.indexOf(quote, at + 1) >= 0) throw new Error('연출 기준 대사가 최종 음성과 다릅니다. 연출을 다시 준비해 주세요.')
        let offset = 0
        const matched = rows.filter(r => { const a = offset; offset += String(r.text || '').length; return a < at + quote.length && offset > at })
        const a = Math.max(0, (Number(matched[0]?.start) - start) / (end - start))
        const b = Math.min(1, (Number(matched.at(-1)?.end) - start) / (end - start))
        if (!Number.isFinite(a + b) || b <= a) throw new Error('연출 대사 구간을 확정 음성에 연결할 수 없습니다.')
        return [a, b] as const
    }
    let from = 0, to = 1
    const quote = String(design.cue?.quote || '')
    const effects = Array.isArray(design.effects) ? design.effects : []
    if (camera.kind !== 'hold') {
        const [a,b] = quoteWindow(quote)
        if (design.cue.phase === 'before') to = a
        else if (design.cue.phase === 'during') { from = a; to = b }
        else if (design.cue.phase === 'after') from = b
        else throw new Error('연출 기준 대사의 시점을 확인해 주세요.')
        if ((to - from) * (end - start) * fps < 3) throw new Error('연출 기준 대사 주변에 움직임을 적용할 시간이 부족합니다.')
    }
    let keys = (camera.unbound_keys || camera.keys).map((k: any) => ({...k, t: from + k.t * (to - from)}))
    if (from > 0) keys.unshift({...keys[0], t: 0})
    if (to < 1) keys.push({...keys.at(-1), t: 1})
    if (keys.length > 8) throw new Error('음성에 맞춘 카메라 키가 너무 많습니다. 경로를 단순화해 주세요.')
    const boundEffects = effects.map((effect: any) => {
        let a=Number(effect.start ?? 0), b=Number(effect.end ?? 1)
        if (effect.event) {
            const [cueStart,cueEnd]=quoteWindow(String(effect.event.quote || ''))
            const phase=effect.event.phase, at=effect.event.at
            const anchor=phase==='before'?cueStart:Number(phase==='after'?cueEnd:(at==='start'?cueStart:at==='end'?cueEnd:(cueStart+cueEnd)/2))
            const span=Number(effect.event.duration_seconds)/(end-start)
            if (!Number.isFinite(anchor+span) || span*(end-start)*fps<3) throw new Error('효과가 확정 음성에서 세 프레임 이상 표시될 수 없습니다.')
            a=Math.max(0,anchor-span/2);b=Math.min(1,anchor+span/2)
            if (b-a < span*.9) { a=Math.max(0,Math.min(1-span,anchor-span/2));b=Math.min(1,a+span) }
        }
        if (!Number.isFinite(a+b) || a<0 || b>1 || b<=a) throw new Error('효과 표시 구간이 장면 타임라인을 벗어납니다.')
        return {type:effect.type,start:a,end:b,intensity:effect.intensity,center:effect.center,radius:effect.radius,color:effect.color,reason:effect.reason}
    })
    const transition=design.transition?.kind ?? 'cut'
    if (!['cut','crossfade'].includes(transition)) throw new Error('지원하지 않는 장면 전환입니다.')
    const transitionSeconds=transition==='crossfade'?Number(design.transition?.duration_seconds ?? .22):0
    if (transition==='crossfade' && (!Number.isFinite(transitionSeconds)||transitionSeconds<.12||transitionSeconds>.6)) throw new Error('디졸브 길이는 0.12~0.6초로 설정해 주세요.')
    return {source, fit: 'cover', direction: direction.visual_strategy, keys, effects:boundEffects, transition,
        transition_seconds:transitionSeconds}
}

export function recordedDirectionFingerprint(payload:any, number:number) {
    const rows=(payload?.subtitles||[]).filter((r:any)=>Number(r.scene_number)===number).map((r:any)=>({
        text:String(r.text||''),start:Number(r.start_num??r.start_time??r.start),end:Number(r.end_num??r.end_time??r.end)}))
    if(!payload?.subtitle_source_audio_id||!rows.length)return null
    const stable=(v:any):any=>Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v
    return createHash('sha256').update(JSON.stringify(stable({audio:payload.subtitle_source_audio_id,rows}))).digest('hex')
}

export function assertRecordedSceneDirections(project:any) {
    for(const scene of project.project_payload?.structure?.scenes||[]) {
        const direction=scene.scene_direction_plan||scene.ae_directorial_plan
        if(!directedScene(direction))continue
        const kind=scene.ae_effect_plan?.enabled?'effect':scene.ae_motion_plan?.enabled?'motion':null
        if(!kind)continue
        const rendered=scene.metadata?.[`ae_${kind}_asset`], number=Number(scene.scene_number||scene.scene_order)
        const expected=recordedDirectionFingerprint(project.project_payload,number)
        if(!expected||rendered?.recorded_direction_binding?.fingerprint!==expected||rendered?.status!=='ready'
            ||rendered?.ae_reviewed!==true||rendered?.source_direction_review?.passed!==true||!rendered?.render_sha256)
            throw new Error(`${number}번 씬은 실제 이미지·확정 음성에 맞춘 연출과 출력 검수가 필요합니다. 임시 연출로 전체 렌더하지 않습니다.`)
    }
}
