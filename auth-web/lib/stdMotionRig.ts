// Native animation data. No AE project execution or expression evaluation.
export type Point = [number,number]
export type Interpolation = 'linear'|'ease'|'ease-in'|'ease-out'|'hold'
export type ValueKey = {t:number;value:number;interpolation?:Interpolation}
export type PointKey = {t:number;x:number;y:number;interpolation?:Interpolation}
export type RigBone = {name:string;parent:number;start:Point;end:Point;keys:ValueKey[];limits?:{min:number;max:number}}
export type MotionRig = {bones:RigBone[];translation?:PointKey[];ik?:{root:number;child:number;bend:1|-1;target:PointKey[]}}
export type MeshPin = {position:Point;radius:number;keys:PointKey[];locked?:boolean}
export type GlowSettings = {threshold:number;softKnee:number;basedOn:'luminance'|'alpha'}
export type NativeEffect = {type:'blur'|'glow'|'fractal_noise'|'turbulent_displace'|'radial_wipe';amount:number;radius:number;seed:number;keys:ValueKey[];glow?:GlowSettings}
export type NativePath = {points:Point[];closed:boolean;color:string;width:number;glow:number;keys:ValueKey[];startKeys?:ValueKey[]}
export type LayerAdvanced = {rig?:MotionRig;mesh?:{columns:number;rows:number;pins:MeshPin[]};effects?:NativeEffect[];mask?:{points:Point[];invert:boolean;feather:number};style?:{stroke:number;strokeColor:string;shadow:number;shadowX:number;shadowY:number;shadowColor:string}}
export type NativeScene = {effects:NativeEffect[];paths:NativePath[]}
export type Matrix = [number,number,number,number,number,number]
export const valueKeys=(end=0):ValueKey[]=>[{t:0,value:0},{t:1,value:end}]
const fail=()=>{throw Error('관절·변형·효과 설정을 확인해 주세요.')}
function n(v:unknown,lo:number,hi:number):number {if(typeof v!=='number'||!Number.isFinite(v)||v<lo||v>hi)fail();return v as number}
function list(v:any,max:number):any[]{if(!Array.isArray(v)||v.length>max)fail();return v}
function point(v:any,lo=0,hi=1):Point {if(!Array.isArray(v)||v.length!==2)fail();return [n(v[0],lo,hi),n(v[1],lo,hi)]}
function sequence<T extends {t:number}>(keys:T[]):T[]{if(keys.length<2||keys[0].t!==0||keys.at(-1)!.t!==1||keys.some((k,i)=>i>0&&k.t<=keys[i-1].t))fail();return keys}
function interpolation(k:any):{interpolation?:Interpolation}{if(k.interpolation===undefined)return {};if(!['linear','ease','ease-in','ease-out','hold'].includes(k.interpolation))fail();return {interpolation:k.interpolation}}
function values(v:any,lo:number,hi:number):ValueKey[]{return sequence(list(v,64).map(k=>({t:n(k?.t,0,1),value:n(k?.value,lo,hi),...interpolation(k)})))}
function positions(v:any):PointKey[]{return sequence(list(v,64).map(k=>({t:n(k?.t,0,1),x:n(k?.x,-1,2),y:n(k?.y,-1,2),...interpolation(k)})))}
function color(v:any):string {if(typeof v!=='string'||!/^#[0-9a-fA-F]{6}$/.test(v))fail();return v}
function points(v:any):Point[]{const p=list(v,128).map(x=>point(x));if(p.length<3)fail();return p}
export const defaultGlow=():GlowSettings=>({threshold:.6,softKnee:.1,basedOn:'luminance'})
export function normalizeNativeEffects(v:any):NativeEffect[]{return list(v,8).map(e=>{if(!e||!['blur','glow','fractal_noise','turbulent_displace','radial_wipe'].includes(e.type))fail();let glow:GlowSettings|undefined;if(e.glow!==undefined){if(e.type!=='glow'||!e.glow||!['luminance','alpha'].includes(e.glow.basedOn))fail();glow={threshold:n(e.glow.threshold,0,1),softKnee:n(e.glow.softKnee,0,1),basedOn:e.glow.basedOn}}return {type:e.type,amount:n(e.amount,0,100),radius:n(e.radius,.001,1),seed:n(e.seed,0,65535),keys:values(e.keys,0,1),...(glow?{glow}:{})}})}
export function normalizeLayerAdvanced(v:any):LayerAdvanced {
    if(!v||typeof v!=='object'||Array.isArray(v))fail();const out:LayerAdvanced={}
    if(v.rig!==undefined){
        const bones:RigBone[]=list(v.rig?.bones,32).map((b,i)=>{if(typeof b?.name!=='string'||b.name.length>80||!Number.isInteger(b.parent)||b.parent< -1||b.parent>=i)fail();const start=point(b.start),end=point(b.end);if(Math.hypot(end[0]-start[0],end[1]-start[1])<.001)fail();let limits;if(b.limits!==undefined){limits={min:n(b.limits.min,-360,360),max:n(b.limits.max,-360,360)};if(limits.min>limits.max)fail()}return {name:b.name,parent:b.parent,start,end,keys:values(b.keys,-360,360),...(limits?{limits}:{})}})
        if(!bones.length)fail();out.rig={bones};if(v.rig.translation!==undefined)out.rig.translation=positions(v.rig.translation)
        if(v.rig.ik!==undefined){const ik=v.rig.ik;if(!Number.isInteger(ik.root)||!Number.isInteger(ik.child)||!bones[ik.root]||!bones[ik.child]||bones[ik.root].parent!==-1||bones[ik.child].parent!==ik.root||![1,-1].includes(ik.bend)||Math.hypot(bones[ik.root].end[0]-bones[ik.child].start[0],bones[ik.root].end[1]-bones[ik.child].start[1])>.001)fail();out.rig.ik={root:ik.root,child:ik.child,bend:ik.bend,target:positions(ik.target)}}
    }
    if(v.mesh!==undefined){const m=v.mesh;if(!Number.isInteger(m?.columns)||!Number.isInteger(m?.rows))fail();out.mesh={columns:n(m.columns,2,24),rows:n(m.rows,2,24),pins:list(m.pins,32).map(p=>{if(p.locked!==undefined&&typeof p.locked!=='boolean')fail();return {position:point(p?.position),radius:n(p?.radius,.01,1),keys:positions(p?.keys),...(p.locked!==undefined?{locked:p.locked}:{})}})}}
    if(v.effects!==undefined)out.effects=normalizeNativeEffects(v.effects)
    if(v.mask!==undefined){if(typeof v.mask?.invert!=='boolean')fail();out.mask={points:points(v.mask.points),invert:v.mask.invert,feather:n(v.mask.feather,0,.1)}}
    if(v.style!==undefined){const s=v.style;out.style={stroke:n(s?.stroke,0,.03),strokeColor:color(s?.strokeColor),shadow:n(s?.shadow,0,.1),shadowX:n(s?.shadowX,-.2,.2),shadowY:n(s?.shadowY,-.2,.2),shadowColor:color(s?.shadowColor)}}
    return out
}
export function normalizeNativeScene(v:any):NativeScene {if(!v||typeof v!=='object')fail();return {effects:normalizeNativeEffects(v.effects),paths:list(v.paths,32).map(p=>{if(typeof p?.closed!=='boolean')fail();return {points:points(p.points),closed:p.closed,color:color(p.color),width:n(p.width,.0001,.1),glow:n(p.glow,0,.1),keys:values(p.keys,0,1),...(p.startKeys!==undefined?{startKeys:values(p.startKeys,0,1)}:{})}})}}
export function interpolateFraction(t:number,mode:Interpolation='linear'):number {const u=Math.max(0,Math.min(1,t));return mode==='hold'?(u===1?1:0):mode==='ease'?u*u*(3-2*u):mode==='ease-in'?u*u:mode==='ease-out'?1-(1-u)*(1-u):u}
export function sampleValue(keys:ValueKey[],t:number):number {const i=keys.findIndex(k=>k.t>=t);if(i<0)return keys.at(-1)!.value;if(!i)return keys[0].value;const a=keys[i-1],b=keys[i];return a.value+(b.value-a.value)*interpolateFraction((t-a.t)/(b.t-a.t),a.interpolation)}
export function samplePoint(keys:PointKey[],t:number):Point {return [sampleValue(keys.map(k=>({t:k.t,value:k.x,interpolation:k.interpolation})),t),sampleValue(keys.map(k=>({t:k.t,value:k.y,interpolation:k.interpolation})),t)]}
export const identity=():Matrix=>[1,0,0,1,0,0]
export function multiply(a:Matrix,b:Matrix):Matrix{return [a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]]}
export const transform=(m:Matrix,p:Point):Point=>[m[0]*p[0]+m[2]*p[1]+m[4],m[1]*p[0]+m[3]*p[1]+m[5]]
function rotate(p:Point,angle:number):Matrix{const c=Math.cos(angle),s=Math.sin(angle);return [c,s,-s,c,p[0]-c*p[0]+s*p[1],p[1]-s*p[0]-c*p[1]]}
export function boneMatrices(rig:MotionRig,t:number,w:number,h:number):Matrix[]{
    const angles=rig.bones.map(b=>sampleValue(b.keys,t)*Math.PI/180)
    if(rig.ik){const {root,child,bend,target}=rig.ik,a=rig.bones[root],b=rig.bones[child],end=samplePoint(target,t),offset=rig.translation?samplePoint(rig.translation,t):[0,0],dx=(end[0]-a.start[0]-offset[0])*w,dy=(end[1]-a.start[1]-offset[1])*h,l1=Math.hypot((a.end[0]-a.start[0])*w,(a.end[1]-a.start[1])*h),l2=Math.hypot((b.end[0]-b.start[0])*w,(b.end[1]-b.start[1])*h),d=Math.max(.00001,Math.min(l1+l2,Math.max(Math.abs(l1-l2)+.00001,Math.hypot(dx,dy)))),elbow=bend*Math.acos(Math.max(-1,Math.min(1,(d*d-l1*l1-l2*l2)/(2*l1*l2)))),base=Math.atan2(dy,dx)-Math.atan2(l2*Math.sin(elbow),l1+l2*Math.cos(elbow)),restA=Math.atan2((a.end[1]-a.start[1])*h,(a.end[0]-a.start[0])*w),restB=Math.atan2((b.end[1]-b.start[1])*h,(b.end[0]-b.start[0])*w);angles[root]=base-restA;angles[child]=elbow-(restB-restA)}
    rig.bones.forEach((b,i)=>{if(b.limits)angles[i]=Math.max(b.limits.min*Math.PI/180,Math.min(b.limits.max*Math.PI/180,angles[i]))});const offset=rig.translation?samplePoint(rig.translation,t):[0,0],root:Matrix=[1,0,0,1,offset[0]*w,offset[1]*h];
    const matrices:Matrix[]=[];rig.bones.forEach((b,i)=>matrices.push(multiply(b.parent<0?root:matrices[b.parent],rotate([b.start[0]*w,b.start[1]*h],angles[i]))));return matrices
}
function segmentDistance(p:Point,a:Point,b:Point){const dx=b[0]-a[0],dy=b[1]-a[1],u=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)));return Math.hypot(p[0]-a[0]-u*dx,p[1]-a[1]-u*dy)}
export function deformPoint(p:Point,advanced:LayerAdvanced,t:number,w:number,h:number,matrices=advanced.rig?boneMatrices(advanced.rig,t,w,h):[]):Point {
    let x=p[0],y=p[1]
    if(advanced.rig){const nearest=advanced.rig.bones.map((b,i)=>({i,d:segmentDistance(p,[b.start[0]*w,b.start[1]*h],[b.end[0]*w,b.end[1]*h])})).sort((a,b)=>a.d-b.d).slice(0,2),weights=nearest.map(b=>1/(1+b.d*b.d)),sum=weights.reduce((a,b)=>a+b,0);x=0;y=0;nearest.forEach((b,i)=>{const q=transform(matrices[b.i],p);x+=q[0]*weights[i]/sum;y+=q[1]*weights[i]/sum})}
    for(const pin of advanced.mesh?.pins||[]){if(pin.locked)continue;const target=samplePoint(pin.keys,t),d=Math.hypot((p[0]/w-pin.position[0]),(p[1]/h-pin.position[1]))/pin.radius,weight=Math.max(0,1-d*d);x+=(target[0]-pin.position[0])*w*weight*weight;y+=(target[1]-pin.position[1])*h*weight*weight}
    // Stationary pins anchor the bind artwork, including deformation from the skeleton.
    let anchor=0;for(const pin of advanced.mesh?.pins||[]){if(!pin.locked)continue;const d=Math.hypot(p[0]/w-pin.position[0],p[1]/h-pin.position[1])/pin.radius;anchor=Math.max(anchor,Math.max(0,1-d*d)**2)}
    return [x+(p[0]-x)*anchor,y+(p[1]-y)*anchor]
}
export function defaultRig():MotionRig {return {bones:[{name:'상완',parent:-1,start:[.5,.2],end:[.5,.5],keys:valueKeys(0)},{name:'하완',parent:0,start:[.5,.5],end:[.5,.8],keys:valueKeys(25)}]}}
export const nativeEffect=(type:NativeEffect['type']):NativeEffect=>({type,amount:type==='radial_wipe'?100:35,radius:.05,seed:7,keys:valueKeys(1),...(type==='glow'?{glow:defaultGlow()}:{})})
/** Calibrated on the retained 1080p violet-pulse AE reference, not universal AE parity. */
export function referenceGlowEffects():NativeEffect[]{const keys=[{t:0,value:1},{t:1,value:1}];return [{...nativeEffect('glow'),amount:10,radius:10/1080,keys,glow:{threshold:0,softKnee:0,basedOn:'alpha'}},{...nativeEffect('blur'),amount:100,radius:5/1080,keys:keys.map(k=>({...k}))}]}
