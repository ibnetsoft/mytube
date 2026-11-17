/** A reviewed anatomy defect cannot acquire optional animation while awaiting repair. */
export function withWuxiaAnatomyHolds(pkg:any,policy:any){
 if(policy?.anatomy_auto?.enabled!==true||policy.anatomy_auto.contract!=='wuxia_anatomy_review/v1'||!Array.isArray(pkg?.scenes))return pkg
 const reviews=pkg.mouth_preparation?.anatomy_reviews
 if(!Array.isArray(reviews))return pkg
 return {...pkg,scenes:pkg.scenes.map((scene:any)=>({...scene,states:(scene.states||[]).map((state:any)=>{
  const review=reviews.find((r:any)=>r.contract==='wuxia_anatomy_review/v1'&&r.source_sha256===state.sha256&&(!r.asset_id||r.asset_id===state.asset_id))
  if(!review||review.passed!==false||!['repair_required','uncertain'].includes(review.decision))return state
  return {...state,anatomy_hold:{source_sha256:state.sha256,decision:review.decision,repair_request:review.repair_request},
   energy_only_motion:true,ambient_loops:[],dialogue_mouths:[],energy_preparation:undefined}
 })}))}
}
