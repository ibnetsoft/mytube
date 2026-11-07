/** Scene-boundary motion uses the editor clock, never CSS or wall-clock timers. */
export const WUXIA_TRANSITIONS = [
 {id:'none',label:'하드 컷'}, {id:'wipe_left',label:'왼쪽 슬라이드'},
 {id:'wipe_right',label:'오른쪽 슬라이드'}, {id:'wipe_up',label:'위로 슬라이드'},
 {id:'wipe_down',label:'아래로 슬라이드'}, {id:'flash',label:'짧은 화이트 플래시'},
 {id:'punch',label:'짧은 펀치 줌'}, {id:'snap_shake',label:'스냅 흔들림'},
 {id:'dissolve',label:'디졸브'}, {id:'fade_out',label:'끝 페이드 아웃'},
] as const
export function wuxiaTransitionFrame(project:any,scene:any,number:number,seconds:number,start:number,end:number,fps=24){
 const p=project?.project_payload||project||{}, pkg=p.structure?.wuxia_ae_package||p.wuxia_ae_package
 const saved=(p.structure?.scenes||p.scenes||[]).find((s:any)=>Number(s.scene_number)===number)
 const requested=String(saved?.metadata?.transition_effect??saved?.transition_effect??scene.transition_effect??'none')
 const kind=({cut:'none',push:'wipe_left',zoom:'punch',brighten:'flash',darken:'fade_out'} as Record<string,string>)[requested]||requested
 const issues:string[]=[]
 if(!WUXIA_TRANSITIONS.some(t=>t.id===kind))issues.push(`unsupported_transition:${requested}`)
 const previous=pkg?.scenes?.[pkg.scenes.indexOf(scene)-1]
 const backdrop=previous?.states?.at(-1)
 if(previous&&!backdrop&&(kind.startsWith('wipe_')||kind==='dissolve'))issues.push('missing_transition_source')
 const duration=Math.min(kind==='flash'?.125:kind==='dissolve'||kind==='fade_out'?.32:.24,(end-start)/2)
 // Quantize exactly as freezeWuxiaScene does, including pause and backward seek.
 const local=Math.max(0,Math.floor((seconds-start)*fps+1e-7)/fps)
 const frames=Math.ceil(end*fps-1e-7)-Math.ceil(start*fps-1e-7)
 const remaining=Math.max(0,(frames-1)/fps-local)
 const progress=Math.min(1,local/duration), ease=1-(1-progress)**3
 const f={contract:'wuxia_transition_samples/v1',kind,dx:0,dy:0,scale:1,opacity:1,flash:0,backdrop:0,issues}
 if(kind==='none'||issues.length)return {...f,source:null}
 if(!Number.isFinite(duration)||duration<=0){issues.push('invalid_transition_duration');return {...f,source:null}}
 if(kind==='fade_out'){f.opacity=Math.min(1,remaining/duration);return {...f,source:null}}
 if(progress<1){
  if(kind.startsWith('wipe_')){
   if(kind==='wipe_left')f.dx=1-ease
   if(kind==='wipe_right')f.dx=ease-1
   if(kind==='wipe_up')f.dy=1-ease
   if(kind==='wipe_down')f.dy=ease-1
   f.backdrop=1
  }
  if(kind==='dissolve'){f.opacity=progress;f.backdrop=1}
  if(kind==='flash')f.flash=.8*(1-progress)
  if(kind==='punch')f.scale=1+.06*(1-ease)
  if(kind==='snap_shake'){f.dx=.006*Math.sin(local*2*Math.PI*10)*(1-progress);f.scale=1.02}
 }
 // Source is still-only and SHA-bound. Never synthesize motion in the preceding cut.
 return {...f,source:(kind.startsWith('wipe_')||kind==='dissolve')?backdrop||null:null}
}
