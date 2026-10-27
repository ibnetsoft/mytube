 'use client'
import {useCallback,useEffect,useState} from 'react'
import {authedFetch,useAuthToken} from '../referrals/_hooks'
const states:Record<string,string>={queued:'대기',pending:'대기',processing:'작업 중',rendering:'조립 중',direction_pending:'실행 검증 대기',direction_approved:'AE 실행 대기',review_pending:'출력 검수 대기',reviewed:'검수 완료',ready:'준비 완료',prepared:'준비 완료',artifact_ready:'씬 제작 완료',completed:'완료',failed:'실패',obsolete:'원본 변경',skipped:'제외',needs_review:'보완 필요',approved:'승인 완료',not_reviewed:'검수 생략',cancelled:'취소'}
const kinds:Record<string,string>={ae_scene_preparation:'PSD·AE 연출 준비',ae_speaker_coordinates:'화자·입 좌표 준비',region_layer_package:'영역 레이어 준비',motion_preview:'연출 준비 / 미리보기',ae_mouth_job:'입모양·준비 씬 제작',motion_automation:'AE 모션 제작',horizontal_webtoon_automation:'AE 가로 웹툰 제작',region_motion_plan:'AE 영역 모션',effectcraft_automation:'EffectCraft · 별도 옵션 이력',filmcraft_automation:'FilmCraft · 별도 옵션 이력',final_render:'최종 영상 조립'}
const stages:Record<string,string>={preparation:'제출 전 · 대본워커',production:'제출 후 · 통합워커',assembly:'최종 조립 · 통합워커'}
const phases:Record<string,string>={mouth_preparation:'화자 추적·입모양 소재 검수',assembly:'장면 전환·음향 최종 조립',direction:'실행 검증·마무리 보정',auto_direction:'실행 검증',render:'AE 실행',production:'씬 제작',review:'출력 검수',auto_review:'출력 검수',auto_enqueue:'최종 조립 등록',final_review:'최종 출력 검수',finalizing:'결과 저장',final_render:'최종 영상 조립',discovery:'대상 확인',needs_review:'보완 필요'}
const group=(s:string)=>['failed','obsolete','needs_review'].includes(s)?'error':['processing','rendering'].includes(s)?'running':['review_pending','direction_pending'].includes(s)?'review':['reviewed','ready','prepared','artifact_ready','completed','approved','skipped','cancelled'].includes(s)?'done':'queue'
export default function Page(){
 const {token,ready}=useAuthToken()
 const [jobs,setJobs]=useState<any[]>([]),[error,setError]=useState(''),[updated,setUpdated]=useState(''),[filter,setFilter]=useState('all'),[search,setSearch]=useState(''),[page,setPage]=useState(0),[hasMore,setHasMore]=useState(false),[selected,setSelected]=useState('')
 const load=useCallback(async()=>{if(!token)return;try{const res=await authedFetch(token,`/api/admin/ae-worker?page=${page}`),body=await res.json();if(!res.ok)throw Error(body.error||'조회 실패');setJobs(body.jobs);setUpdated(body.generatedAt);setHasMore(body.hasMore);setError('')}catch(e:any){setError(e.message||'조회 실패')}},[token,page])
 useEffect(()=>{void load();const timer=setInterval(()=>void load(),15000);return()=>clearInterval(timer)},[load])
 if(!ready)return <main className="p-6">로그인 확인 중…</main>
 if(!token)return <main className="p-6">관리자 로그인이 필요합니다. <a href="/">로그인으로 이동</a></main>
 const shown=jobs.filter(j=>(filter==='all'||group(j.state)===filter)&&`${j.title} ${j.topicId||''} ${j.projectId}`.toLowerCase().includes(search.toLowerCase()))
 const projects=new Map<string,any[]>()
 for(const job of shown)projects.set(job.projectId,[...(projects.get(job.projectId)||[]),job])
 const detail=jobs.find(j=>j.id===selected)
 return <main className="min-h-screen bg-[#10131b] p-6 text-white"><div className="mx-auto max-w-6xl space-y-5">
  <div className="flex flex-wrap justify-between gap-3"><h1 className="text-2xl font-bold">After Effects 제작 현황</h1><button onClick={()=>void load()} className="rounded bg-blue-600 px-4 py-2">새로고침</button></div>
  <p className="text-sm text-gray-300">대본워커의 연출·소재 준비 → 유저웹 확인·제출 → 통합워커의 AE 실행·출력 검수 → 최종 영상 조립을 프로젝트별로 확인합니다.</p>
  <p className="text-xs text-gray-400">15초 자동 갱신 · 모든 활성 작업 + 이력 종류별 100건/페이지 · 컴퓨터 온라인 여부와 작업 완료는 별개입니다. 대체 엔진의 기존 작업도 이력으로 표시합니다.</p>
  <p className="text-xs text-gray-400">최근 조회: {updated?new Date(updated).toLocaleString('ko-KR'):'조회 중'}</p>
  {error&&<p role="alert" className="text-red-300">{error}</p>}
  <label className="block">프로젝트 검색<input className="ml-3 rounded bg-white/10 p-2" value={search} onChange={e=>setSearch(e.target.value)} placeholder="제목·토픽·프로젝트 ID"/></label>
  <div className="flex flex-wrap gap-2">{[['all','전체'],['queue','대기'],['running','작업 중'],['review','검수·검증 대기'],['done','단계 완료'],['error','오류·보완']].map(([key,label])=><button key={key} aria-pressed={filter===key} onClick={()=>setFilter(key)} className={`rounded px-3 py-2 ${filter===key?'bg-blue-600':'bg-white/10'}`}>{label} {jobs.filter(j=>key==='all'||group(j.state)===key).length}</button>)}</div>
  {!shown.length&&<p>표시할 작업이 없습니다.</p>}
  {Array.from(projects.entries()).map(([id,items])=><section key={id} className="space-y-3 rounded-xl border border-white/20 p-4"><h2 className="text-lg font-semibold">{items[0].title}{items[0].topicId?` · 토픽 ${items[0].topicId}`:''}</h2><p className="text-xs text-gray-400">프로젝트 {id}</p>{items.map(j=><button key={j.id} onClick={()=>setSelected(j.id)} className={`block w-full rounded border p-3 text-left ${selected===j.id?'border-blue-400':'border-white/10'}`}><div className="flex flex-wrap justify-between gap-2"><strong>{kinds[j.kind]||j.kind}</strong><span>{states[j.state]||j.state}</span></div><p className="mt-1 text-sm text-gray-300">{stages[j.stage]} · {j.engine}{j.phase?` · ${phases[j.phase]||j.phase}`:''}</p>{j.kind==='final_render'?<><p>조립 진행률 {j.completed}%</p><progress aria-label="최종 조립 진행률" className="w-full" max={100} value={j.completed}/></>:<p className="text-sm">{j.target?`씬 결과 ${j.completed}/${j.target}`:'대상 씬 확인 중'}{j.progress?` · ${j.progress}`:''}</p>}<p className="mt-1 text-xs text-gray-400">갱신 {new Date(j.updatedAt).toLocaleString('ko-KR')}</p>{j.error&&<p className="mt-2 text-red-300">{j.error}</p>}</button>)}</section>)}
  <nav aria-label="작업 이력 페이지" className="flex gap-4 items-center"><button disabled={page===0} onClick={()=>setPage(p=>p-1)} className="rounded bg-white/10 p-2 disabled:opacity-40">이전 이력</button><span>{page+1}페이지</span><button disabled={!hasMore} onClick={()=>setPage(p=>p+1)} className="rounded bg-white/10 p-2 disabled:opacity-40">다음 이력</button></nav>
  {detail&&<section className="rounded-xl border border-blue-400 p-4"><h2 className="font-semibold">{kinds[detail.kind]} · 씬별 결과</h2><p className="text-xs text-gray-400">작업 {detail.id}</p>{!detail.results.length&&<p className="mt-2 text-sm">아직 씬별 결과가 없거나 개별 준비·최종 조립 작업입니다.</p>}{detail.results.map((r:any)=><article key={r.number} className="mt-3 rounded bg-white/5 p-3"><p>{r.number}씬 · {states[r.status]||r.status} · {r.speakers.join(', ')||'화자 없음'}</p><p className="text-sm text-gray-400">{r.note}</p>{r.videoUrl&&<a className="text-blue-300 underline" href={r.videoUrl} target="_blank" rel="noopener noreferrer">씬 영상 보기</a>}</article>)}</section>}
  <a href="/dashboard" className="inline-block text-blue-300 underline">관리자 화면으로 돌아가기</a>
 </div></main>
}
