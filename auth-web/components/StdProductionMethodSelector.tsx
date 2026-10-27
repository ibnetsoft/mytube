'use client'
import type {ProductionMethod} from '@/lib/stdMotionStudio'
import {alternativeEnginesEnabled} from '../lib/stdProductionEnginePolicy'
export default function StdProductionMethodSelector({method,disabled,onSelect}:{method:ProductionMethod;disabled:boolean;onSelect:(method:ProductionMethod)=>void}){
    return <fieldset disabled={disabled} className="mx-5 space-y-3 rounded-xl border border-cyan-500/30 bg-[#101722] p-4 text-white">
        <legend className="px-2 font-semibold">영상 제작 방식</legend>
        <p className="text-sm text-slate-300">대본워커에서 연출·좌표·레이어를 준비하고, 유저웹에서 확인·제출하면 통합워커가 After Effects를 실행합니다. 최종 영상은 기본 FFmpeg로 조립합니다.</p>
        <div className="grid gap-3 md:grid-cols-2">
            <label className={`cursor-pointer rounded-lg border p-3 ${method==='ae'?'border-cyan-300 bg-cyan-950':'border-slate-600'}`}><input type="radio" name="production-method" value="ae" checked={method==='ae'} onChange={()=>onSelect('ae')}/> After Effects · 기본 제작<p className="mt-2 text-xs text-slate-300">준비된 소재·연출에 확정 음성의 시간을 적용해 로컬 AE에서 씬 영상을 제작합니다.</p></label>
        </div>
        <details><summary className="cursor-pointer text-sm text-slate-400">별도 제작 옵션 · {alternativeEnginesEnabled?'활성':'현재 비활성'}</summary>
        <p className="my-2 text-xs text-slate-400">EffectCraft·FilmCraft·브라우저 제작은 별도 보관합니다. 비활성 상태에서는 선택·제출·실행할 수 없습니다. 기존 설정과 결과는 유지됩니다.</p>
        <fieldset disabled={!alternativeEnginesEnabled} className="grid gap-3 md:grid-cols-2">
            <label className={`cursor-pointer rounded-lg border p-3 ${method==='motion_studio'?'border-cyan-300 bg-cyan-950':'border-slate-600'}`}><input type="radio" name="production-method" value="motion_studio" checked={method==='motion_studio'} onChange={()=>onSelect('motion_studio')}/> Motion Studio · 추가 옵션<p className="mt-2 text-xs text-slate-300">별도 웹 편집·브라우저 제작 방식을 선택합니다. AI 영상 혼합은 이 옵션 안에서 별도로 선택합니다. 기존 워커를 대체하지 않습니다.</p></label>
            <label className={`cursor-pointer rounded-lg border p-3 ${method==='effectcraft'?'border-cyan-300 bg-cyan-950':'border-slate-600'}`}><input type="radio" name="production-method" value="effectcraft" checked={method==='effectcraft'} onChange={()=>onSelect('effectcraft')}/> Motion Studio · EffectCraft<p className="mt-2 text-xs text-slate-300">준비된 원본·레이어·연출을 제출하면 통합워커의 EffectCraft 엔진으로 제작합니다. 초기 통합 · 실제 영상 검증 전이며, 워커에 엔진 설치가 필요합니다.</p></label>
            <label className={`cursor-pointer rounded-lg border p-3 ${method==='filmcraft'?'border-cyan-300 bg-cyan-950':'border-slate-600'}`}><input type="radio" name="production-method" value="filmcraft" checked={method==='filmcraft'} onChange={()=>onSelect('filmcraft')}/> FilmCraft · 네이티브 씬 효과 · 추가 옵션<p className="mt-2 text-xs text-slate-300">이미지·영상의 카메라·벡터 효과도 FilmCraft에서 제작하는 별도 옵션입니다. AE·EffectCraft 선택과 최종 렌더 설정은 독립적입니다.</p></label>
        </fieldset></details>
    </fieldset>
}
