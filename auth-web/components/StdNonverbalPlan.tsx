'use client'
import { isNonverbalProject, nonverbalStructure } from '@/lib/stdNonverbal'
import StdRegionMotionEditor from './StdRegionMotionEditor'
export default function StdNonverbalPlan({project,headers,locale='ko',onApplied}:{project:any;headers:Record<string,string>;locale?:string;onApplied?:()=>void}) {
    if (!isNonverbalProject(project)) return null
    const structure=nonverbalStructure(project)
    const th=locale==='th'
    return <section className="w-full space-y-4 rounded-xl border border-cyan-600/40 bg-[#191e27] p-5 select-text">
        <h2 className="text-lg font-bold text-cyan-200">{th?'แอนิเมชันเด็กเล็กไร้บทพูด':'논버벌 유아 애니메이션'}</h2>
        <p className="text-gray-300">{th?'ใช้เรื่องราวผ่านการกระทำและเวลา ไม่มีเสียงบรรยายหรือคำบรรยาย เตรียมชิ้นส่วนที่สมบูรณ์ ตรวจส่วนซ้อนข้อต่อ แล้วเรนเดอร์ด้วย AE':'나레이션·자막 대신 행동과 장면 시간을 사용합니다. 완성된 부품을 준비하고 관절 겹침을 확인한 뒤 AE로 렌더합니다.'}</p>
        <p className="whitespace-pre-wrap">{structure.story_outline}</p>
        <StdRegionMotionEditor projectId={project.id} headers={headers} locale={locale} onApplied={onApplied}/>
        <details><summary className="cursor-pointer text-cyan-300">{th?'ตัวละครและชิ้นส่วนที่ใช้ซ้ำ':'캐릭터·재사용 부품 프롬프트'}</summary>
            {(structure.character_rigs || []).map((rig:any)=><div key={rig.character_id} className="mt-3 space-y-2">
                <h3 className="font-bold">{rig.name}</h3><p className="whitespace-pre-wrap">{rig.reference_prompt}</p>
                {(rig.parts || []).map((p:any)=><details key={p.id} className="rounded border border-white/10 p-2"><summary>{p.name} · {p.parentId || 'root'}</summary>
                    <p className="mt-2 whitespace-pre-wrap">{p.image_prompt}</p><p className="mt-2 text-amber-200 whitespace-pre-wrap">{p.overlap_prompt}</p>
                </details>)}
            </div>)}
        </details>
        {(structure.scenes || []).map((scene:any)=><details key={scene.scene_number} className="rounded border border-white/10 p-3">
            <summary className="cursor-pointer">{scene.scene_number} · {scene.duration_seconds}s · {scene.action_summary}</summary>
            <p className="mt-2 whitespace-pre-wrap">{scene.direction_prompt}</p>
            <ul className="mt-2 space-y-1">{(scene.timed_beats || []).map((beat:any,i:number)=><li key={i}>{beat.start_seconds}–{beat.end_seconds}s · {beat.target} · {beat.action}</li>)}</ul>
            <p className="mt-3 text-cyan-200">{th?'ภาพฉาก':'장면 이미지'}</p><p className="whitespace-pre-wrap">{scene.image_prompt}</p>
            <p className="mt-3 text-cyan-200">{th?'พื้นหลังไม่มีตัวละคร':'캐릭터 없는 빈 배경'}</p><p className="whitespace-pre-wrap">{scene.background_prompt}</p>
        </details>)}
        <details className="rounded border border-white/10 p-3"><summary>{th?'เพลงและเสียงประกอบ':'음악·효과음 연출'}</summary>
            <p className="mt-2 whitespace-pre-wrap">{structure.audio_plan?.bgm_prompt}</p>
            <ul className="mt-2">{(structure.audio_plan?.sfx_cues || []).map((cue:any,i:number)=><li key={i}>{cue.scene_number} · {cue.at_seconds}s · {cue.description}</li>)}</ul>
        </details>
        <p className="text-amber-200">{th?'แผนพร้อมแล้ว ยังต้องสร้างและตรวจภาพจริง เพลง เสียงประกอบ และผล AE':'기획 준비 완료와 실제 영상 완성은 별개입니다. 원화·음악·효과음 파일과 AE 결과 검수가 필요합니다.'}</p>
    </section>
}
