import type {WebMotionInsert} from './stdMotionStudio'
export type HybridRow={number:number;start:number;end:number;sourceStart:number;sourceEnd:number;clip:{id:string;from:number;to:number}}
export type HybridSegment={kind:'native'|'ai';number:number;clipId:string;start:number;end:number;motionRange:[number,number];videoRange?:[number,number];jobId?:string}
/** Inserts use original scene seconds. Intersections follow every split/repeated/retimed clip. */
export function planHybridTimeline(rows:HybridRow[],inserts:Record<string,WebMotionInsert>):HybridSegment[]{
 const result:HybridSegment[]=[]
 for(const row of rows){const duration=row.sourceEnd-row.sourceStart,from=row.clip.from,to=row.clip.to,a=from*duration,b=to*duration,plan=inserts[String(row.number)]
  if(!Number.isFinite(duration)||duration<=0||!Number.isFinite(row.start)||!Number.isFinite(row.end)||row.end<=row.start||!Number.isFinite(from)||!Number.isFinite(to)||from<0||to>1||b<=a)throw Error('혼합 타임라인의 원본·클립 구간을 확인해 주세요.')
  const time=(s:number)=>row.start+(s-a)/(b-a)*(row.end-row.start),native=(l:number,r:number)=>{if(r-l>1e-9)result.push({kind:'native',number:row.number,clipId:row.clip.id,start:time(l),end:time(r),motionRange:[l/duration,r/duration]})}
  if(!plan){native(a,b);continue}
  if(!Number.isFinite(plan.start)||!Number.isFinite(plan.duration)||plan.start<0||plan.duration<=0||plan.start+plan.duration>duration+.001||!plan.job_id)throw Error(`${row.number}번 AI 구간이 원본 씬 길이를 초과하거나 유효하지 않습니다.`)
  const left=Math.max(a,plan.start),right=Math.min(b,plan.start+plan.duration)
  if(right-left<=1e-9){native(a,b);continue}
  native(a,left);result.push({kind:'ai',number:row.number,clipId:row.clip.id,start:time(left),end:time(right),motionRange:[0,1],videoRange:[left-plan.start,right-plan.start],jobId:plan.job_id});native(right,b)
 }
 if(result.some((s,i)=>i>0&&Math.abs(s.start-result[i-1].end)>.001))throw Error('혼합 타임라인에 빈 구간이 있습니다.')
 return result
}
