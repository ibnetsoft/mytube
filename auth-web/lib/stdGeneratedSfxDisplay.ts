/** Display saved prompts without invoking generation or inferring cut IDs from numbers. */
const object=(v:any):any=>{if(typeof v==='string'){try{return JSON.parse(v)}catch{return null}}return v&&typeof v==='object'?v:null}
export function generatedSfxRows(project:any):any[] {
    const p=object(project?.project_payload),s=object(project?.source_payload)
    const plan=[p?.sfx_generation_plan,p?.structure?.sfx_generation_plan,s?.pregenerated_structure?.sfx_generation_plan].map(object).find(v=>v?.contract==='elevenlabs_sfx_plan/v1'&&Array.isArray(v.cues))
    return (plan?.cues||[]).filter((c:any)=>typeof c.id==='string'&&/^C\d{3}$/.test(c.cut_id)&&typeof c.prompt==='string'&&Number.isFinite(c.duration_seconds)&&c.duration_seconds>0&&Number.isFinite(c.offset_seconds)&&c.offset_seconds>=0&&Number.isFinite(c.volume_db))
}
export function generatedSfxForScene(project:any,scene:any,number:number):any[] {
    const p=object(project?.project_payload)
    const rows=[scene,...(p?.scenes||[]),...(p?.structure?.scenes||[])].filter(r=>r&&Number(r.scene_number??r.scene_order)===Number(number))
    const ids=[...new Set(rows.flatMap(r=>[r.cut_id,r.metadata?.cut_id]).filter(v=>/^C\d{3}$/.test(v||'')))]
    return ids.length===1?generatedSfxRows(project).filter(c=>c.cut_id===ids[0]):[]
}
