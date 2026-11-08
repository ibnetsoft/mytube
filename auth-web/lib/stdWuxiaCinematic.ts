import { wuxiaTextLines } from './stdWuxiaGraphic'
export const CINEMATIC='wuxia_cinematic/v1'
export function cinematicPlan(project:any,number:number){const s=(project?.project_payload||project)?.structure;const policy=s?.wuxia_cinematic_policy||s?.wuxia_mouth_policy?.cinematic_auto;return policy?.enabled===true?policy.selections?.[String(number)]:undefined}
export const canonical=(v:any):string=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x)
export function cinematicReviewMatches(state:any,plan:any,graphics:any[]=[]){return state?.cinematic_review?.contract===CINEMATIC&&state.cinematic_review.source_sha256===state.sha256&&canonical(state.cinematic_review.plan)===canonical(plan)&&canonical(state.cinematic_review.graphics||[])===canonical(graphics)}
export function cinematicFrame(project:any,scene:any,state:any,number:number,seconds:number,start:number,end:number,transition:any,motion:any,fps=24){
 const plan=cinematicPlan(project,number),r=state?.cinematic_review
 const out:any={contract:CINEMATIC,vignette_opacity:0,panel_opacity:0,panel_scale:1,blur_radius:0,blur_axis:'x',descriptor:{mask:null,panel:null,lettering_boxes:[]},issues:[],notes:[]}
 if(!plan||!cinematicReviewMatches(state,plan,scene.graphics||[])||r.passed!==true||state.energy_only_motion===true)return out
 const at=Math.floor(Math.max(0,seconds-start)*fps+1e-7)/fps,total=end-start,stateStart=Number(state.start||0)*total,stateEnd=Number(state.end??1)*total,t=at-stateStart,duration=stateEnd-stateStart
 if(plan.vignette&&r.vignette_allowed){out.descriptor.mask={center:r.focus,protected_boxes:r.protected_boxes};out.vignette_opacity=.38*Math.max(0,Math.min(1,t/.18,(duration-t)/.18))}
 if(plan.panel&&r.panel_allowed){
  const box=r.panel_rect,w=(box[2]-box[0])*1920,h=(box[3]-box[1])*1080,lines=wuxiaTextLines(plan.panel_text,w-40,36),size=Math.min(36,(h-36)/(lines.length*1.3))
  const hold=Math.max(1.8,Math.min(4,plan.panel_text.length*.045+1.2)),window=hold+.5,u=t-.2
  if(duration<window+.2||size<24)out.notes.push('panel_suppressed_readability_window')
  else{
   out.descriptor.panel={rect:box,lines,font_size:size,bounce:plan.bounce};out.panel_opacity=Math.max(0,Math.min(1,u/.12,(window-u)/.18))
   if(plan.bounce&&u>=0&&u<.32){const keys=[[0,.86],[.12,1.08],[.22,.98],[.32,1]];const i=keys.findIndex((k,n)=>n>0&&u<=k[0]);const a=keys[Math.max(0,i-1)],b=keys[i];if(b){const p=(u-a[0])/(b[0]-a[0]);out.panel_scale=a[1]+(b[1]-a[1])*(1-(1-p)**3)}}
  }
 }
 out.descriptor.lettering_boxes=r.lettering_boxes||[]
 if(plan.slide_blur&&r.slide_blur_allowed&&transition.kind.startsWith('wipe_')&&!motion.heat?.length){const progress=Math.min(1,Math.max(0,at)/Math.min(.24,total/2));out.blur_radius=12*(1-progress);out.blur_axis=['wipe_up','wipe_down'].includes(transition.kind)?'y':'x'}
 return out
}
/** Static source-reviewed mask. Browser and native use the same 960x540 alpha formula. */
export function cinematicMask(mask:any,width=960,height=540){
 const data=new Uint8ClampedArray(width*height*4),[cx,cy]=mask.center
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){
  const nx=x/(width-1),ny=y/(height-1),radius=Math.hypot((nx-cx)/Math.max(cx,1-cx),(ny-cy)/Math.max(cy,1-cy))/Math.SQRT2
  let alpha=Math.max(0,Math.min(1,(radius-.15)/.65))**1.2
  for(const b of mask.protected_boxes){const dx=Math.max(b[0]-nx,0,nx-b[2])*1920,dy=Math.max(b[1]-ny,0,ny-b[3])*1080;alpha*=Math.min(1,Math.hypot(dx,dy)/20)}
  data[(y*width+x)*4+3]=Math.floor(alpha*255+.5)
 }
 return data
}
