/** Display-only authored outgoing boundaries. Never infer cut IDs from scene numbers. */
export type WorkerTransition = { id:string; from:string; to:string; label:string; seconds:number; reason:string; state:'planned'|'blocked'|'clip_internal' }
const obj=(v:any):any=>{if(typeof v==='string'){try{return JSON.parse(v)}catch{return null}}return v&&typeof v==='object'?v:null}
const cut=(v:any)=>/^C#?\d{3}$/.test(String(v||''))?String(v).replace('#',''):''
function summary(row:any):WorkerTransition|null {
    const from=cut(row?.from_cut_id),to=cut(row?.to_cut_id),seconds=row?.duration_seconds
    if(!from||!to||from===to||typeof seconds!=='number'||!Number.isFinite(seconds)||seconds<0||seconds>1||typeof row?.effect_label!=='string'||!row.effect_label.trim())return null
    return {id:String(row.transition_id||from+'-'+to),from,to,label:row.effect_label.slice(0,100),seconds,reason:String(row.reason||'').slice(0,500),state:row.readiness==='blocked_source'||row.blocked_cut_ids?.length?'blocked':row.execution_owner==='video_clip_internal_edit'?'clip_internal':'planned'}
}
export function workerTransitionPlan(project:any):any|null {
    const p=obj(project?.project_payload),s=obj(project?.source_payload)
    const candidates=[p?.structure?.cut_transition_plan,p?.cut_transition_plan,s?.pregenerated_structure?.cut_transition_plan,s?.structure?.cut_transition_plan,s?.cut_transition_plan]
    return candidates.map(obj).find(v=>v?.contract==='manual_cut_transition_plan/v1'&&Array.isArray(v.transitions))||null
}
export function workerTransitionList(project:any):WorkerTransition[]{
    const plan=workerTransitionPlan(project);return (plan?.transitions||[]).map(summary).filter((r:WorkerTransition|null):r is WorkerTransition=>!!r)
}
export function workerTransitionForScene(project:any,scene:any,number:number):WorkerTransition|null {
    const p=obj(project?.project_payload)
    const rows=[scene,...(Array.isArray(p?.scenes)?p.scenes:[]),...(Array.isArray(p?.structure?.scenes)?p.structure.scenes:[])]
        .filter(r=>r&&Number(r.scene_number??r.scene_order)===Number(number))
    // Explicit ID only. A 16-scene script and a 120-cut board are different indices.
    const ids=[...new Set(rows.flatMap(r=>[cut(r.cut_id),cut(r.metadata?.cut_id)]).filter(Boolean))]
    if(ids.length!==1)return null
    const id=ids[0]
    const row=workerTransitionPlan(project)?.transitions.find((r:any)=>cut(r.from_cut_id)===id)
    if(row)return summary(row)
    const direct=rows.map(r=>r.outgoing_transition||r.metadata?.outgoing_transition).find(r=>cut(r?.from_cut_id)===id)
    return summary(direct)
}
