/** Frozen, approved prompt data only. Provider calls belong to submitted workers. */
export function approvedGeneratedSfxPlan(project:any) {
    const payload=project.project_payload||{}
    const plan=payload.sfx_generation_plan||payload.structure?.sfx_generation_plan
    if(!plan)return null
    if(plan.contract!=='elevenlabs_sfx_plan/v1'||plan.status!=='approved'||!Array.isArray(plan.cues)||plan.cues.length>120)
        throw new Error('효과음 프롬프트 단계를 확인·확정해 주세요.')
    return plan
}
export function freezeGeneratedSfx(project:any, scenes:any[], clock:any[]) {
    const plan=approvedGeneratedSfxPlan(project)
    if(!plan)return null
    const payload=project.project_payload||{}
    const ids=new Set<string>(), cuts=payload.structure?.manual_image_prompts?.cuts||[]
    const cues=plan.cues.map((cue:any)=>{
        if(typeof cue.id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(cue.id)||ids.has(cue.id)||typeof cue.cut_id!=='string')throw new Error('효과음 ID·컷 연결을 확인해 주세요.')
        ids.add(cue.id)
        if(typeof cue.prompt!=='string'||!cue.prompt.trim()||cue.prompt.length>2000)throw new Error('효과음 영문 프롬프트가 필요합니다.')
        for(const [key,lo,hi] of [['duration_seconds',.5,30],['offset_seconds',0,3600],['volume_db',-60,0]] as const)
            if(typeof cue[key]!=='number'||!Number.isFinite(cue[key])||cue[key]<lo||cue[key]>hi)throw new Error('효과음 길이·시점·음량을 확인해 주세요.')
        const cutRows=cuts.filter((r:any)=>r.cut_id===cue.cut_id)
        const sceneId=cutRows.length===1&&cuts.filter((r:any)=>r.scene_id===cutRows[0].scene_id).length===1?cutRows[0].scene_id:null
        const exact=scenes.filter((s:any)=>(s.cut_id||s.metadata?.cut_id)===cue.cut_id)
        const mapped=exact.length?exact:sceneId?scenes.filter((s:any)=>(s.scene_id||s.metadata?.scene_id)===sceneId):[]
        if(mapped.length!==1)throw new Error(`${cue.cut_id} 효과음의 확정 컷을 찾을 수 없습니다.`)
        const number=Number(mapped[0].scene_number??mapped[0].number), t=clock.find((s:any)=>s.number===number)
        if(!t||!Number.isFinite(t.start)||!Number.isFinite(t.end)||t.end<=t.start||cue.offset_seconds>=t.end-t.start)throw new Error(`${cue.cut_id} 효과음 위치가 확정 씬을 벗어납니다.`)
        return {...cue,scene_number:number,start:t.start+cue.offset_seconds,end:t.end,source_asset_id:t.source?.id||null}
    })
    return {contract:'elevenlabs_sfx_frozen/v1',project_id:project.id,cues}
}
