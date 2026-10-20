'use client'
import type {ProductionMethod} from '@/lib/stdMotionStudio'
export default function StdProductionMethodSelector({method,disabled,onSelect}:{method:ProductionMethod;disabled:boolean;onSelect:(method:ProductionMethod)=>void}){
    return <fieldset disabled={disabled} className="mx-5 space-y-3 rounded-xl border border-cyan-500/30 bg-[#101722] p-4 text-white">
        <legend className="px-2 font-semibold">제작 방식 선택</legend>
        <p className="text-sm text-slate-300">기존 AE 제작을 기본으로 사용합니다. Motion Studio는 필요할 때 선택하는 추가 옵션입니다. 방식별 연출 설정은 각각 보관됩니다.</p>
        <div className="grid gap-3 md:grid-cols-3">
            <label className={`cursor-pointer rounded-lg border p-3 ${method==='ae'?'border-cyan-300 bg-cyan-950':'border-slate-600'}`}><input type="radio" name="production-method" value="ae" checked={method==='ae'} onChange={()=>onSelect('ae')}/> 기존 AE 방식 · 기본<p className="mt-2 text-xs text-slate-300">기존 PSD 장면 연출·AE 효과·모션 제작과 제출 흐름을 사용합니다. 대본 워커와 렌더 워커를 유지합니다.</p></label>
            <label className={`cursor-pointer rounded-lg border p-3 ${method==='motion_studio'?'border-cyan-300 bg-cyan-950':'border-slate-600'}`}><input type="radio" name="production-method" value="motion_studio" checked={method==='motion_studio'} onChange={()=>onSelect('motion_studio')}/> Motion Studio · 추가 옵션<p className="mt-2 text-xs text-slate-300">별도 웹 편집·브라우저 제작 방식을 선택합니다. AI 영상 혼합은 이 옵션 안에서 별도로 선택합니다. 기존 워커를 대체하지 않습니다.</p></label>
            <label className={`cursor-pointer rounded-lg border p-3 ${method==='effectcraft'?'border-cyan-300 bg-cyan-950':'border-slate-600'}`}><input type="radio" name="production-method" value="effectcraft" checked={method==='effectcraft'} onChange={()=>onSelect('effectcraft')}/> Motion Studio · EffectCraft<p className="mt-2 text-xs text-slate-300">준비된 원본·레이어·연출을 제출하면 통합워커의 EffectCraft 엔진으로 제작합니다. 초기 통합 · 실제 영상 검증 전이며, 워커에 엔진 설치가 필요합니다.</p></label>
        </div>
    </fieldset>
}
