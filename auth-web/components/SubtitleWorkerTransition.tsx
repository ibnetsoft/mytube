import { workerTransitionForScene, workerTransitionList, type WorkerTransition } from '@/lib/stdWorkerTransitions'
const timing=(r:WorkerTransition)=>r.seconds===0?'즉시':`${r.seconds.toFixed(2)}초`
const state=(r:WorkerTransition)=>r.state==='blocked'?'원화 확인 전 보류':r.state==='clip_internal'?'클립 내부 편집':'저장 지침'
export function SubtitleWorkerTransition({project,scene,number}:{project:any;scene:any;number:number}) {
    const r=workerTransitionForScene(project,scene,number)
    if(!r)return null
    return <div data-worker-transition={r.id} className="mt-1 rounded border border-violet-400/20 bg-violet-500/10 p-1 text-[10px] text-violet-200" title={r.reason}>
        <span className="block">다음 컷 전환 · {r.from} → {r.to}</span>
        <span className="block">{r.label} · {timing(r)} · {state(r)}</span>
    </div>
}
export function SubtitleWorkerTransitionList({project}:{project:any}) {
    const rows=workerTransitionList(project)
    if(!rows.length)return null
    return <details className="mx-2 my-2 rounded border border-violet-400/20 p-2 text-xs text-violet-200" data-worker-transition-list>
        <summary className="cursor-pointer">대본워커 전환 지침 · {rows.length}개</summary>
        <p className="my-2 text-gray-400">컷 ID가 연결된 씬에는 다음 컷 전환을 표시합니다. 번호가 다른 대본과 컷 목록은 임의로 연결하지 않습니다. 이 표시는 실제 미리보기·AE 렌더 적용 확인과 별도입니다.</p>
        <div className="max-h-72 overflow-auto space-y-2">{rows.map(r=><div key={r.id} data-worker-boundary={r.id} className="border-b border-white/10 pb-1">
            <p>{r.from} → {r.to} · {r.label} · {timing(r)} · {state(r)}</p><p className="text-gray-400">{r.reason}</p>
        </div>)}</div>
    </details>
}
