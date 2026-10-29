import { createHash } from 'crypto'
export const SAVED_SCENE_BINDING = 'saved_scene_execution/v1'
const numberOf=(s:any)=>Number(s?.scene_number??s?.scene_order??s?.number)
const object=(v:any):any=>{if(typeof v==='string'){try{return JSON.parse(v)}catch{return null}}return v}
const clamp=(v:any,fallback:number,lo:number,hi:number)=>Number.isFinite(Number(v))?Math.max(lo,Math.min(hi,Number(v))):fallback
export function savedScene(project:any,number:number){
    const structures=[project.project_payload?.structure,project.project_payload,project.source_payload?.structure,project.source_payload?.pregenerated_structure,project.source_payload]
    let result:any=null
    for(const value of [...structures].reverse()){const s=object(value);if(Array.isArray(s?.scenes)){const row=s.scenes.find((r:any)=>numberOf(r)===number);if(row)result={...(result||{}),...row}}}
    return result
}
export function hasSavedSceneExecution(project:any){
    const structures=[project.project_payload?.structure,project.project_payload,project.source_payload?.structure,project.source_payload?.pregenerated_structure,project.source_payload]
    const numbers=new Set<number>()
    for(const value of structures){const s=object(value);for(const row of Array.isArray(s?.scenes)?s.scenes:[])if(Number.isSafeInteger(numberOf(row)))numbers.add(numberOf(row))}
    return [...numbers].some(n=>{const row=savedScene(project,n);const d=object(row?.scene_direction_plan||row?.ae_directorial_plan);return d?.contract==='scene_direction_plan/v1'&&Array.isArray(d.ae_operations)&&d.ae_operations.some((op:string)=>op!=='hold')})
}
/** Bind numbered authored v1 scenes, never assign an unnumbered preset catalogue by array index. */
export function bindSavedSceneExecution(authored:any,source:string,start:number,end:number,preparation?:any){
    const legacy=object(authored?.scene_direction_plan||authored?.ae_directorial_plan)
    if(legacy?.contract!=='scene_direction_plan/v1'||!Array.isArray(legacy.ae_operations))return null
    if(!Number.isFinite(start+end)||end<=start)throw Error('저장 연출의 확정 음성 구간이 유효하지 않습니다.')
    const duration=end-start,number=numberOf(authored),operations=[...new Set<string>(legacy.ae_operations)]
    const base=(t:number,scale=1,x=.5,y=.5)=>({t,x,y,scale,rotation:0,opacity:100})
    const binding:any={contract:SAVED_SCENE_BINDING,scene_number:number,source_contract:legacy.contract,
        authored_sha256:createHash('sha256').update(JSON.stringify(legacy)).digest('hex'),
        timing:{start,end,clock:'finalized_narration'},requested_operations:operations,applied_operations:[],pending_requirements:[],
        zoom_policy:'no_slow_zoom/v1',status:'bound'}
    const direction:any={source,fit:'contain',keys:[base(0),base(1)],effects:[],lights:[],transition:'cut',transition_seconds:0,
        direction:'저장된 씬별 연출 연결 · 중간속도 동작만 사용 · 느린 줌 금지'}
    if(source==='video'){
        binding.status='source_preserved';binding.reason='업로드 영상의 원래 카메라·동작 유지';return {direction,binding}
    }
    const prepared=preparation?.metadata?.result?.plan
    const roles=new Set((prepared?.layers||[]).map((l:any)=>l.role))
    const depthReady=['background','character','foreground'].every(r=>roles.has(r))
    if(operations.includes('depth_parallax')&&!depthReady){
        binding.status='needs_layers';binding.pending_requirements.push({operation:'depth_parallax',required_layers:['background','character','foreground'],reason:'실제 승인 레이어 필요; 평면 줌을 패럴랙스로 대체하지 않음'})
    }
    const span=Math.min(2,Math.max(.15,duration-.2)),from=Math.min(.1,duration*.05),to=Math.min(duration,from+span)
    const a=from/duration,b=to/duration
    if(operations.includes('camera_move')){
        const delta=clamp(legacy.effect_limits?.max_scale_delta,.04,.02,.08)
        const x=.5+(clamp(legacy.focus_target?.x,.5,0,1)-.5)*delta
        const y=.5+(clamp(legacy.focus_target?.y,.5,0,1)-.5)*delta
        direction.fit='cover';direction.keys=[base(0),base(a),base(b,1+delta,x,y),base(1,1+delta,x,y)].filter((k,i,all)=>i===0||k.t>all[i-1].t)
        binding.applied_operations.push('camera_move');binding.camera_seconds=to-from
    }
    const center=[clamp(legacy.focus_target?.x,.5,0,1),clamp(legacy.focus_target?.y,.5,0,1)]
    if(operations.includes('atmosphere_drift')){
        direction.effects.push({type:'atmospheric_haze',start:0,end:1,intensity:clamp(legacy.effect_limits?.intensity,.08,.05,.12),center,radius:.65,color:[1,1,1],reason:String(legacy.dramatic_intent||legacy.visual_strategy||'저장된 분위기 연출')})
        binding.applied_operations.push('atmosphere_drift')
    }
    if(operations.includes('light_flicker')){
        direction.lights.push({color:[1,.9,.75],center,radius:.25,keys:[{t:0,opacity:0},{t:a,opacity:0},{t:(a+b)/2,opacity:6},{t:b,opacity:0},{t:1,opacity:0}].filter((k,i,all)=>i===0||k.t>all[i-1].t)})
        binding.applied_operations.push('light_flicker')
    }
    if(operations.includes('depth_parallax')&&depthReady){
        direction.layer_motion={contract:SAVED_SCENE_BINDING,from:a,to:b,move_x:-.012,roles:['background','character','foreground']}
        binding.applied_operations.push('depth_parallax')
    }
    const supported=new Set(['hold','camera_move','atmosphere_drift','light_flicker','depth_parallax'])
    for(const op of operations.filter(o=>!supported.has(o)))binding.pending_requirements.push({operation:op,reason:'별도 소재·실행 계획 필요'})
    if(binding.pending_requirements.length&&binding.status!=='needs_layers')binding.status='partially_bound'
    return {direction,binding}
}
