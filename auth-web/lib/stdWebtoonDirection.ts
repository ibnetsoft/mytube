export type DirectionCue = {id:string;start:number;end:number;kind:'push'|'shake'|'reveal';target:string;amount:number}
export function normalizeDirectionCues(raw:unknown):DirectionCue[]{
    if(!Array.isArray(raw)||raw.length>64)throw Error('장면 연출은 64개 이하로 설정해 주세요.')
    const ids=new Set<string>(),reveals=new Set<string>()
    return raw.map(c=>{
        if(!c||typeof c.id!=='string'||!/^[\w-]{1,80}$/.test(c.id)||ids.has(c.id)||!['push','shake','reveal'].includes(c.kind)
            ||typeof c.target!=='string'||!c.target||c.target.length>80||![c.start,c.end,c.amount].every(Number.isFinite)
            ||c.start<0||c.end>1||c.end<=c.start||c.amount<0||c.amount>1)throw Error('연출 대상·시작·종료·강도를 확인해 주세요.')
        if(c.kind==='reveal'){if(reveals.has(c.target))throw Error('같은 대상의 등장 연출은 한 개만 설정해 주세요.');reveals.add(c.target)}
        ids.add(c.id);return {id:c.id,start:c.start,end:c.end,kind:c.kind,target:c.target,amount:c.amount}
    })
}
export function validateDirectionTargets(cues:DirectionCue[]|undefined,layerIds:string[]){
    const available=new Set(['camera',...layerIds])
    if(cues?.some(c=>!available.has(c.target)))throw Error('연출 대상 레이어가 원본에 없습니다. 연출 대상을 다시 선택해 주세요.')
}
export function directionPose<T extends {scale:number;x:number;opacity:number}>(pose:T,cues:DirectionCue[]|undefined,target:string,t:number):T{
    const result={...pose}
    for(const cue of cues||[]){
        if(cue.target!==target||t<cue.start)continue
        const u=Math.max(0,Math.min(1,(t-cue.start)/(cue.end-cue.start))),ease=u*u*(3-2*u)
        if(cue.kind==='push')result.scale*=1+.08*cue.amount*ease
        if(cue.kind==='reveal')result.opacity*=1-cue.amount+cue.amount*ease
        if(cue.kind==='shake'&&t<cue.end)result.x+=Math.sin(u*Math.PI*12)*Math.sin(u*Math.PI)*.008*cue.amount
    }
    // Reveal remains hidden before its cue, then stays visible after it.
    for(const cue of cues||[])if(cue.target===target&&cue.kind==='reveal'&&t<cue.start)result.opacity*=1-cue.amount
    result.scale=Math.min(2,Math.max(.1,result.scale));result.x=Math.max(0,Math.min(1,result.x));result.opacity=Math.max(0,Math.min(100,result.opacity))
    return result
}
export function boundaryWindow(boundary:number,total:number,padding=1.5){
    if(!Number.isFinite(boundary+total+padding)||total<=0||boundary<0||boundary>total||padding<=0)throw Error('장면 경계 시간을 확인해 주세요.')
    return {start:Math.max(0,boundary-padding),end:Math.min(total,boundary+padding)}
}
/** Trim a timeline while retaining each shot's original motion and video sample range. */
export function sliceMotionShots<T extends {start:number;end:number;motionRange?:[number,number];videoRange?:[number,number];originStart?:number;originEnd?:number}>(shots:T[],start:number,end:number):T[]{
    if(!Number.isFinite(start+end)||start<0||end<=start||end>(shots.at(-1)?.end||0)+.001)throw Error('부분 제작 구간을 확인해 주세요.')
    return shots.filter(s=>s.end>start&&s.start<end).map(s=>{
        const a=Math.max(start,s.start),b=Math.min(end,s.end),range=(r:[number,number]):[number,number]=>[r[0]+(r[1]-r[0])*(a-s.start)/(s.end-s.start),r[0]+(r[1]-r[0])*(b-s.start)/(s.end-s.start)]
        return {...s,start:a-start,end:b-start,motionRange:range(s.motionRange||[0,1]),...(s.videoRange?{videoRange:range(s.videoRange)}:{}),originStart:(s.originStart??s.start)-start,originEnd:(s.originEnd??s.end)-start}
    })
}
