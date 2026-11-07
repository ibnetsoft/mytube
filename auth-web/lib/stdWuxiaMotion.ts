/** Bounded opening camera move plus sampled, spatially varying heat refraction. */
export const WUXIA_PANS=[{id:'none',label:'이동 없음'},{id:'pan_right',label:'좌 → 우'},{id:'pan_left',label:'우 → 좌'},{id:'pan_up',label:'아래 → 위'},{id:'pan_down',label:'위 → 아래'}] as const
export const WUXIA_ZOOMS=[{id:'none',label:'줌 없음'},{id:'zoom_in',label:'줌인'},{id:'zoom_out',label:'줌아웃'}] as const
export const WUXIA_MOTIONS=WUXIA_PANS.flatMap(p=>WUXIA_ZOOMS.map(z=>({id:p.id==='none'?z.id:z.id==='none'?p.id:`${p.id}_${z.id}`,label:[p.id==='none'?'':p.label,z.id==='none'?'':z.label].filter(Boolean).join(' + ')||'고정'})))
export function wuxiaMotionValue(scene:any){return String(scene?.metadata?.image_effect??scene?.image_effect??'none')}
export function wuxiaMotionSpeed(scene:any){const raw=Number(scene?.metadata?.motion_speed??scene?.motion_speed??1);return Number.isFinite(raw)&&raw>0?Math.max(.5,Math.min(3,raw)):1}
export function splitWuxiaMotion(value:string){
 const [id,...suffix]=value.split('+'),pan=WUXIA_PANS.find(p=>p.id!=='none'&&id.startsWith(p.id))?.id||'none'
 const zoom=WUXIA_ZOOMS.find(z=>z.id!=='none'&&id.endsWith(z.id))?.id||'none'
 return {id,pan,zoom,heat:suffix.includes('heat'),valid:WUXIA_MOTIONS.some(m=>m.id===id)&&suffix.length<=1&&suffix.every(s=>s==='heat')}
}
export function joinWuxiaMotion(pan:string,zoom:string,heat:boolean){return (pan==='none'?zoom:zoom==='none'?pan:`${pan}_${zoom}`)+(heat?'+heat':'')}
export const HEAT_BANDS=48
export function wuxiaMotionFrame(project:any,scene:any,state:any,number:number,seconds:number,start:number,end:number,fps=24){
 if(state?.energy_only_motion===true)return {contract:'wuxia_motion_samples/v1',active:false,dx:0,dy:0,scale:1,heat:[],issues:[]}
 const p=project?.project_payload||project||{},saved=(p.structure?.scenes||p.scenes||[]).find((s:any)=>Number(s.scene_number)===number)
 const selection=splitWuxiaMotion(wuxiaMotionValue(saved||scene)),issues:string[]=[]
 if(!selection.valid)issues.push('unsupported_wuxia_motion')
 const speed=wuxiaMotionSpeed(saved||scene)
 const strength=scene.motion_strength??1
 const validStrength=typeof strength==='number'&&Number.isFinite(strength)&&strength>=.25&&strength<=1
 if(!validStrength)issues.push('invalid_motion_strength')
 const amount=validStrength?strength:1
 const local=Math.max(0,Math.floor((seconds-start)*fps+1e-7)/fps),duration=Math.min(1.2,.9/speed,Math.max(1/fps,end-start-1/fps))
 const t=Math.min(1,local/duration),progress=t*t*(3-2*t),pan=selection.pan!=='none'
 const scale=(pan?1+.12*amount:1)+(selection.zoom==='zoom_in'?.12*amount*progress:selection.zoom==='zoom_out'?.12*amount*(1-progress):0)
 const offset=.03*amount*(2*progress-1)
 const dx=selection.pan==='pan_right'?offset:selection.pan==='pan_left'?-offset:0
 const dy=selection.pan==='pan_down'?offset:selection.pan==='pan_up'?-offset:0
 const heat:number[]=[]
 if(selection.heat&&state?.heat_shimmer_enabled!==false){
  const faces=state?.face_exclusion_boxes
  const hands=state?.hand_exclusion_boxes,regions=state?.protected_regions
  const boxes=[...(Array.isArray(faces)?faces:[]),...(Array.isArray(hands)?hands:[]),...(Array.isArray(regions)?regions:[])]
  if(!Array.isArray(faces))issues.push('missing_heat_face_review')
  const validBoxes=(hands==null||Array.isArray(hands))&&(regions==null||Array.isArray(regions))&&boxes.every(b=>Array.isArray(b)&&b.length===4&&b.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1)&&b[0]<b[2]&&b[1]<b[3])
  if(!validBoxes)issues.push('invalid_heat_protection')
  const range=state?.heat_shimmer_vertical_range??[0,1]
  const validRange=Array.isArray(range)&&range.length===2&&range.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1)&&range[0]<range[1]
  if(!validRange)issues.push('invalid_heat_range')
  const envelope=Math.max(0,Math.min(1,local/.25,(end-start-local-1/fps)/.25))
  for(let i=0;i<HEAT_BANDS;i++){
   const top=i/HEAT_BANDS,bottom=(i+1)/HEAT_BANDS
   // Entire horizontal strips containing reviewed anatomy remain unwarped, with a guard band.
   const protectedRow=!validRange||top<range[0]||bottom>range[1]||!Array.isArray(faces)||!validBoxes||boxes.some(b=>top<b[3]+.025&&bottom>b[1]-.025)
   heat.push(protectedRow?0:Math.round(envelope*(3.5*Math.sin(i*.44-local*10.7)+1.5*Math.sin(i*.19-local*7.1))*1000)/1000)
  }
 }
 return {contract:'wuxia_motion_samples/v1',active:selection.id!=='none'||selection.heat,dx,dy,scale:Math.round(scale*1e6)/1e6,heat,issues}
}
