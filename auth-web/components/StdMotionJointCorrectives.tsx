'use client'
import type {MotionRig} from '@/lib/stdMotionRig'
import type {JointCorrective} from '@/lib/stdMotionCorrectives'
import StdMotionKeyTimeline from './StdMotionKeyTimeline'

export default function StdMotionJointCorrectives({rig,boneIndex,onBone,onChange,time,onSeek,duration,fps}:{rig:MotionRig;boneIndex:number;onBone:(i:number)=>void;onChange:(r:MotionRig)=>void;time:number;onSeek?:(t:number)=>void;duration:number;fps:number}){
    const bone=rig.bones[boneIndex],poses=rig.correctives||[],regions=rig.regions||[]
    const update=(index:number,patch:Partial<JointCorrective>)=>onChange({...rig,correctives:poses.map((p,i)=>i===index?{...p,...patch}:p)})
    const add=(kind:'어깨'|'팔꿈치'|'골반')=>onChange({...rig,correctives:[...poses,{bone:boneIndex,angle:90,center:[...bone.start],radius:kind==='골반'?[.16,.13]:kind==='어깨'?[.12,.12]:[.08,.1],scale:kind==='팔꿈치'?[1.15,1.05]:[1.08,1.08],offset:[0,0],strength:.5}]})
    return <details className="space-y-2 rounded border border-cyan-800 p-2"><summary>관절 보정 포즈 · 부위 겹침</summary>
        <label className="block text-xs">편집 관절 <select aria-label="보정 관절" className="bg-slate-800" value={boneIndex} onChange={e=>onBone(Number(e.target.value))}>{rig.bones.map((b,i)=><option key={i} value={i}>{b.name}</option>)}</select></label>
        <p className="text-xs">보정은 IK 계산 후의 관절 각도로 작동합니다. 중심·반경을 실제 그림에 맞추고 양방향 포즈를 각각 검수하세요.</p>
        <div className="flex gap-2">{(['어깨','팔꿈치','골반'] as const).map(kind=><button key={kind} type="button" disabled={poses.length>=32} onClick={()=>add(kind)}>{kind} 보정 추가</button>)}</div>
        {poses.map((pose,index)=>pose.bone===boneIndex&&<fieldset key={index} className="space-y-1 border border-slate-700 p-2"><legend>{bone.name} 보정 {index+1}</legend>
            {([{key:'angle',label:'작동 각도',min:-180,max:180,step:1},{key:'strength',label:'보정 강도',min:0,max:1,step:.05}] as const).map(field=><label key={field.key} className="mr-3 inline-block text-xs">{field.label}<input aria-label={`${field.label} ${index+1}`} className="ml-1 w-20 bg-slate-800" type="number" {...{min:field.min,max:field.max,step:field.step}} value={pose[field.key]} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=field.min&&v<=field.max&&(field.key!=='angle'||Math.abs(v)>=1))update(index,{[field.key]:v})}}/></label>)}
            {([{key:'center',label:'중심',min:0,max:1},{key:'radius',label:'반경',min:.005,max:.5},{key:'scale',label:'형태 배율',min:.5,max:1.5},{key:'offset',label:'보정 이동',min:-.1,max:.1}] as const).map(field=><div key={field.key} className="text-xs">{field.label}{([0,1] as const).map(axis=><label key={axis} className="ml-2">{axis===0?'X':'Y'}<input aria-label={`${field.label} ${axis===0?'X':'Y'} ${index+1}`} className="ml-1 w-20 bg-slate-800" type="number" min={field.min} max={field.max} step=".005" value={pose[field.key][axis]} onChange={e=>{const v=Number(e.target.value);if(!Number.isFinite(v)||v<field.min||v>field.max)return;const pair:[number,number]=[...pose[field.key]];pair[axis]=v;update(index,{[field.key]:pair})}}/></label>)}</div>)}
            <button type="button" onClick={()=>onChange({...rig,correctives:poses.filter((_,i)=>i!==index)})}>이 보정 삭제</button>
        </fieldset>)}
        <StdMotionKeyTimeline key={`depth-${boneIndex}`} label="부위 앞뒤 순서" keys={bone.depth||[{t:0,value:0},{t:1,value:0}]} time={time} onSeek={onSeek} duration={duration} fps={fps} min={-100} max={100} onChange={depth=>onChange({...rig,bones:rig.bones.map((b,i)=>i===boneIndex?{...b,depth}:b)})}/>
        <p className="text-xs">가중치가 있는 메시에서 값이 큰 부위를 앞으로 합성합니다. 교차 순간에는 유지 보간을 사용하세요. 숨은 원화 복원·자동 충돌 처리는 포함되지 않습니다.</p>
        <div className="space-y-2 border-t border-slate-700 pt-2"><p className="text-xs">얼굴은 머리 관절로 영역 고정하면 몸을 따라 회전하면서 형태를 유지합니다. 다른 인물은 원화 위치 유지로 보호하세요. 뒤의 영역이 우선합니다.</p>
            {[-1,boneIndex].map(target=><button key={target} type="button" className="mr-3" disabled={regions.length>=32} onClick={()=>onChange({...rig,regions:[...regions,{bone:target,min:[.2,.1],max:[.5,.4],feather:.02}]})}>{target<0?'원화 위치 유지 영역 추가':'선택 관절 고정 영역 추가'}</button>)}
            {regions.map((region,index)=><fieldset key={index} className="border border-slate-700 p-2"><legend>보호 영역 {index+1} · {region.bone<0?'원화 위치':rig.bones[region.bone].name}</legend>
                {(['min','max'] as const).map(edge=><div key={edge} className="text-xs">{edge==='min'?'왼쪽 위':'오른쪽 아래'}{([0,1] as const).map(axis=><label key={axis} className="ml-2">{axis===0?'X':'Y'}<input className="w-20 bg-slate-800" aria-label={`보호 ${edge} ${axis} ${index+1}`} type="number" min="0" max="1" step=".005" value={region[edge][axis]} onChange={e=>{const v=Number(e.target.value);if(!Number.isFinite(v)||v<0||v>1||(edge==='min'?v>=region.max[axis]:v<=region.min[axis]))return;const point:[number,number]=[...region[edge]];point[axis]=v;onChange({...rig,regions:regions.map((r,i)=>i===index?{...r,[edge]:point}:r)})}}/></label>)}</div>)}
                <label className="text-xs">경계 부드러움<input className="w-20 bg-slate-800" aria-label={`보호 경계 ${index+1}`} type="number" min="0" max=".1" step=".005" value={region.feather} onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=0&&v<=.1)onChange({...rig,regions:regions.map((r,i)=>i===index?{...r,feather:v}:r)})}}/></label>
                <button type="button" className="ml-3" onClick={()=>onChange({...rig,regions:regions.filter((_,i)=>i!==index)})}>보호 영역 {index+1} 삭제</button>
            </fieldset>)}
        </div>
    </details>
}

