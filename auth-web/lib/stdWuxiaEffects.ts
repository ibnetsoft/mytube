import { wuxiaGraphicBounds } from './stdWuxiaGraphic'
/** Deterministic short accents. Frozen vector/transform samples are executed verbatim by AE. */
export const WUXIA_FX_CONTRACT='wuxia_effect_samples/v1'
const types=new Set(['impact_shake','impact_flash','debris_burst','particle_burst','speedline_burst','focus_glow','shock_ring'])
const overlaps=(a:number[],b:number[])=>a[0]<b[2]&&a[2]>b[0]&&a[1]<b[3]&&a[3]>b[1]
const finite=(v:any)=>typeof v==='number'&&Number.isFinite(v)
export function wuxiaEffectFrame(scene:any,state:any,graphics:any[],seconds:number,start:number,end:number,resolve:(g:any)=>any,fps=24){
 const at=Math.floor(Math.max(0,seconds-start)*fps+1e-7)/fps+start
 const frame:any={contract:WUXIA_FX_CONTRACT,dx:0,dy:0,scale:1,overlays:[],active:[],issues:[]}
 const heads=state?.face_exclusion_boxes
 const textBoxes=graphics.filter(g=>g.layout?.center&&g.layout?.size).map(g=>wuxiaGraphicBounds(g).map((v,i)=>v/(i%2?1080:1920)))
 const protectedBoxes=[...(Array.isArray(heads)?heads:[]),...textBoxes]
 for(const [index,e] of (scene.effects||[]).entries()){
  if(!types.has(e.type)||!finite(e.duration_seconds)||e.duration_seconds<=0||e.duration_seconds>.8||!finite(e.intensity)||e.intensity<=0||e.intensity>1||!Array.isArray(e.center)||e.center.length!==2||e.center.some((n:any)=>!finite(n)||n<0||n>1)||!finite(e.radius)||e.radius<=0||e.radius>1){frame.issues.push(`invalid_effect:${index}`);continue}
  if(e.amplitude_px!=null&&(!finite(e.amplitude_px)||e.amplitude_px<=0||e.amplitude_px>16)){frame.issues.push(`invalid_amplitude:${index}`);continue}
  const target=e.asset_id||scene.states?.[Math.max(0,(e.state||1)-1)]?.asset_id
  const range=resolve({voice_binding:e.voice_binding,text:e.quote})
  const from=range?(e.voice_binding?.phase==='after'?range.end:range.start):start+Number(e.preview_at||0)*(end-start)
  if(e.voice_binding?.exact_anchor&&!range){frame.issues.push(`unmatched_effect_anchor:${index}`);continue}
  const t=(at-from)/e.duration_seconds
  if(t<0||t>=1||target!==(state?.parent_asset_id||state?.asset_id))continue
  if(e.camera_face_boxes && (e.source_sha256!==state?.sha256 || !Array.isArray(e.camera_face_boxes) || e.camera_face_boxes.some((b:any)=>!Array.isArray(b)||b.length!==4||b.some((v:any)=>!finite(v)||v<0||v>1)||b[0]>=b[2]||b[1]>=b[3]))){frame.issues.push(`invalid_camera_face_review:${index}`);continue}
  if(!Array.isArray(heads)){frame.issues.push(`missing_head_review:${index}`);continue}
  frame.active.push(`${e.type}:${index}`)
  const strength=e.intensity,fade=Math.sin(Math.PI*t),cx=e.center[0],cy=e.center[1],radius=e.radius
  if(e.type==='impact_shake'){
   const amp=e.amplitude_px??(4+12*strength),dx=Math.sin(t*Math.PI*9)*amp*(1-t),dy=Math.sin(t*Math.PI*13)*amp*.45*(1-t),scale=e.amplitude_px?1+amp/400:1.035
   const moved=(e.camera_face_boxes||heads).map((b:number[])=>b.map((v:number,i:number)=>(v-.5)*scale+.5+(i%2?dy/1080:dx/1920)))
   if(moved.some((b:number[])=>b.some((n:number)=>n<0||n>1)||textBoxes.some(r=>overlaps(b,r)))){frame.issues.push(`unsafe_shake:${index}`);continue}
   frame.dx+=dx;frame.dy+=dy;frame.scale=scale;continue
  }
  const add=(shape:any,box:number[])=>{if(!protectedBoxes.some(b=>overlaps(box,b)))frame.overlays.push(shape)}
  const color=e.type==='debris_burst'?'#b7a38a':e.type==='focus_glow'?'#e7bc68':'#fff5dc'
  if(['impact_flash','focus_glow','shock_ring'].includes(e.type)){
   const r=radius*(e.type==='shock_ring'?.3+.7*t:1),opacity=fade*strength*(e.type==='impact_flash'?.35:.18)
   add({kind:'ellipse',cx:cx*1920,cy:cy*1080,rx:r*1920,ry:r*1080,color,opacity,stroke:e.type==='shock_ring'?3:0},[cx-r,cy-r,cx+r,cy+r]);continue
  }
  for(let i=0;i<12;i++){
   const angle=i*2.399963,travel=radius*(.12+.85*t),x=cx+Math.cos(angle)*travel,y=cy+Math.sin(angle)*travel*.65+t*t*radius*.35,size=(2+i%3)*strength+1
   if(e.type==='speedline_burst'){
    const x2=cx+Math.cos(angle)*radius,y2=cy+Math.sin(angle)*radius*.65
    add({kind:'line',points:[[x*1920,y*1080],[x2*1920,y2*1080]],color,opacity:fade*strength*.55,width:2},[Math.min(x,x2)-.003,Math.min(y,y2)-.003,Math.max(x,x2)+.003,Math.max(y,y2)+.003])
   }else add({kind:'polygon',points:[[x*1920-size,y*1080],[x*1920+size,y*1080-size],[x*1920+size*.5,y*1080+size]],color,opacity:(1-t)*strength*.8,stroke:0},[x-size/1920,y-size/1080,x+size/1920,y+size/1080])
  }
 }
 return frame
}
