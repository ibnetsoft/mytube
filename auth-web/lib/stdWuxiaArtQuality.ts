/** Source-bound actual anatomy approval is required before using reviewed artwork. */
export function withWuxiaAnatomyHolds(pkg:any,policy:any){
 if(!Array.isArray(pkg?.scenes))return pkg
 const enabled=policy?.anatomy_auto?.enabled===true&&policy.anatomy_auto.contract==='wuxia_anatomy_review/v1'
 const report=Array.isArray(pkg.mouth_timing?.anatomy_reviews)?pkg.mouth_timing:pkg.mouth_preparation||{},reviews=report.anatomy_reviews||[]
 if(!enabled&&!reviews.length)return pkg
 return {...pkg,scenes:pkg.scenes.map((scene:any)=>({...scene,states:(scene.states||[]).map((original:any)=>{
  const replacement=(report.anatomy_replacements||[]).find((r:any)=>r.original_source_sha256===original.sha256&&r.state?.asset_id===original.asset_id)
  const approvedReplacement=replacement&&reviews.some((r:any)=>r.contract==='wuxia_anatomy_review/v1'&&r.asset_id===original.asset_id&&r.source_sha256===replacement.state.sha256&&r.passed===true&&r.decision==='passed')
  const state=approvedReplacement?{...original,...replacement.state,ambient_loops:[],dialogue_mouths:[],energy_preparation:undefined,cinematic_review:undefined,anatomy_hold:undefined}:original
  const review=reviews.find((r:any)=>r.contract==='wuxia_anatomy_review/v1'&&r.source_sha256===state.sha256&&(!r.asset_id||r.asset_id===state.asset_id))
  if(review?.passed===true&&review.decision==='passed')return {...state,anatomy_approval:{source_sha256:state.sha256,decision:'passed',contract:review.contract}}
  if(!enabled&&!review)return state
  return {...state,anatomy_hold:{source_sha256:state.sha256,decision:review?.decision||'review_required',repair_request:review?.repair_request},
   energy_only_motion:true,ambient_loops:[],dialogue_mouths:[],energy_preparation:undefined}
 })}))}
}
export function assertWuxiaArtUsable(state:any){
 if(state?.anatomy_hold)throw Error('해부학 검수를 통과하지 않은 원화입니다. 수정·재생성 후 재검수가 필요합니다.')
}
