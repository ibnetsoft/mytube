'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import Image from 'next/image'

const imageStyles = [
    { key: 'realistic', name: '실사' },
    { key: 'cinematic', name: '시네마틱' },
    { key: 'anime', name: '애니메이션' },
    { key: 'ghibli', name: '지브리' },
    { key: 'webtoon', name: '웹툰' },
    { key: 'korean_webtoon', name: '한국 웹툰' },
    { key: '3d', name: '3D' },
    { key: 'minimal', name: '미니멀' },
    { key: 'wimpy', name: '윔피' },
]

type Item = { id: string; title: string; status: string; review_note: string; created_at: string; job_status: string | null; ae_scene_delivery: 'local' | 'gcs' }
const statuses: Record<string, string> = { pending: '승인 대기', approved: '승인됨', rejected: '반려', queued: '실행 대기', running: '대본 작성 중', failed: '작성 실패', interrupted: '작업 중단', awaiting_approval: '대본 검토 대기', approved_pending_repair: '대본 승인됨', completed: '완료' }
export default function TopicSubmissionPanel({ headers }: { headers: Record<string, string> }) {
    const [items, setItems] = useState<Item[]>([])
    const [images, setImages] = useState<{ name: string; data: string }[]>([])
    const [busy, setBusy] = useState(false)
    const [reading, setReading] = useState(false)
    const [error, setError] = useState('')
    const [notice, setNotice] = useState('')
    const [loading, setLoading] = useState(true)
    const submission = useRef({ key: '', body: '' })
    const inFlight = useRef(false)
    const load = useCallback(async () => {
        try {
            const res = await fetch('/api/std/topic-submissions', { headers })
            const data = await res.json()
            if (!res.ok) throw new Error(data.error)
            setItems(data.items)
        } catch (e) { setError(e instanceof Error ? e.message : '목록 조회 실패') }
        finally { setLoading(false) }
    }, [headers])
    useEffect(() => { void load(); const timer = setInterval(load, 15000); return () => clearInterval(timer) }, [load])
    const input = 'mt-2 w-full rounded-lg border border-white/15 bg-[#11141a] p-3 text-sm text-gray-100'
    async function selectImages(files: FileList | null) {
        if (!files) return
        setReading(true); setError('')
        try {
            if (files.length > 3) throw new Error('이미지는 최대 3장입니다.')
            const result = await Promise.all(Array.from(files).map(async file => {
                if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 512000) throw new Error('PNG/JPEG/WebP 이미지, 장당 500KB 이하로 선택하세요.')
                const data = await new Promise<string>((resolve, reject) => {
                    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsDataURL(file)
                })
                return { name: file.name.slice(0, 120), data }
            }))
            setImages(result)
        } catch (e) { setImages([]); setError(e instanceof Error ? e.message : '이미지 읽기 실패') }
        finally { setReading(false) }
    }
    return <section className="mx-auto w-full max-w-5xl space-y-6 select-text">
        <div><h1 className="text-2xl font-semibold">토픽 등록</h1><p className="mt-2 text-gray-400">이야기와 참고 자료를 등록하세요. 로컬 대본워커에서 검토·승인 후 대본 작성을 시작합니다.</p></div>
        {error && <p role="alert" className="rounded-lg bg-red-500/10 p-3 text-red-300">{error}</p>}
        {notice && <p role="status" className="rounded-lg bg-emerald-500/10 p-3 text-emerald-300">{notice}</p>}
        <form className="rounded-xl border border-white/10 bg-[#191e27] p-5 space-y-5" onSubmit={async event => {
            event.preventDefault(); if (inFlight.current || reading) return
            const form = event.currentTarget
            const data = Object.fromEntries(new FormData(form).entries()); delete data.images
            const body = JSON.stringify({ ...data, duration_minutes: Number(data.duration_minutes), character_images: images })
            if (submission.current.body !== body) submission.current = { key: crypto.randomUUID(), body }
            inFlight.current = true; setBusy(true); setError(''); setNotice('')
            try {
                const res = await fetch('/api/std/topic-submissions', { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json', 'Idempotency-Key': submission.current.key }, body })
                const result = await res.json(); if (!res.ok) throw new Error(result.error)
                form.reset(); setImages([]); submission.current = { key: '', body: '' }
                setNotice('토픽을 등록했습니다. 로컬 대본워커의 승인 대기열에 표시됩니다.'); await load()
            } catch (e) { setError(e instanceof Error ? e.message : '등록 실패') }
            finally { inFlight.current = false; setBusy(false) }
        }}>
            <fieldset disabled={busy} className="space-y-5">
                <label className="block">토픽 제목 *<input name="title" required maxLength={200} className={input} placeholder="이야기의 제목" /></label>
                <label className="block">유튜브 URL<input name="youtube_url" type="url" maxLength={2048} className={input} placeholder="https://www.youtube.com/watch?v=..." /></label>
                <label className="block">스토리 개략적인 내용 *<textarea name="story" required maxLength={2500} rows={5} className={input} placeholder="주요 사건, 갈등, 반전과 원하는 결말을 적어주세요." /></label>
                <div className="grid gap-4 sm:grid-cols-2">
                    <label>캐릭터 설명<textarea name="character_notes" maxLength={1500} rows={4} className={input} placeholder="이름, 성격, 관계, 말투와 이미지별 캐릭터 이름" /></label>
                    <label>캐릭터 이미지<input name="images" type="file" multiple accept="image/png,image/jpeg,image/webp" className={input} disabled={reading} onChange={e => void selectImages(e.target.files)} /><span className="block mt-2 text-gray-400">최대 3장 · 장당 500KB · PNG/JPEG/WebP</span></label>
                </div>
                {images.length > 0 && <div className="flex gap-3 flex-wrap">{images.map((image, i) => <figure key={i}><img src={image.data} alt={image.name} className="h-28 w-28 rounded-lg object-contain bg-black/20" /><figcaption className="max-w-28 truncate mt-1">{image.name}</figcaption></figure>)}</div>}
                <div className="grid gap-4 sm:grid-cols-3">
                    <label>카테고리 *<input name="category" required defaultValue="옛날이야기" maxLength={80} className={input} /></label>
                    <label>분량 (분)<input name="duration_minutes" type="number" required min={1} max={60} defaultValue={15} className={input} /></label>
                    <label>대본 언어<select name="language" className={input}><option value="ko">한국어</option><option value="en">영어</option><option value="ja">일본어</option><option value="es">스페인어</option></select></label>
                    <label>배경 국가 *<input name="setting_country" required defaultValue="한국" maxLength={80} className={input} /></label>
                    <label>시대·지역 *<input name="era_region" required defaultValue="현대 지방 소도시" maxLength={120} className={input} /></label>
                    <label>제작 모드<select name="production_mode" className={input}><option value="standard">기존 영상</option><option value="moving_comic">무빙툰</option></select></label>
                </div>
                <fieldset>
                    <legend className="font-semibold">이미지 스타일 *</legend>
                    <p className="mt-1 text-sm text-gray-400">원하는 분위기의 썸네일을 선택하세요.</p>
                    <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                        {imageStyles.map(style => <label key={style.key} className="relative cursor-pointer">
                            <input type="radio" name="image_style" value={style.key} defaultChecked={style.key === 'realistic'} required aria-label={style.name} className="peer sr-only" />
                            <span className="block overflow-hidden rounded-xl border-2 border-white/10 bg-[#11141a] transition peer-checked:border-indigo-400 peer-checked:bg-indigo-500/15 peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-4 peer-focus-visible:outline-indigo-300 peer-disabled:opacity-50 hover:border-white/40">
                                <span className="relative block aspect-[4/3]">
                                    <Image src={`/img/styles/style_${style.key}.png`} alt={`${style.name} 스타일 예시`} fill sizes="(max-width: 639px) 45vw, (max-width: 1023px) 30vw, 180px" className="object-cover" />
                                </span>
                                <span className="block px-3 py-2.5 text-sm font-medium">{style.name}</span>
                            </span>
                            <span aria-hidden="true" className="absolute right-2 top-2 hidden rounded-full bg-indigo-500 px-2 py-1 text-xs font-semibold text-white peer-checked:block">✓ 선택됨</span>
                        </label>)}
                    </div>
                </fieldset>
                <fieldset className="rounded-lg border border-white/15 p-4">
                    <legend className="px-1 font-semibold">AE 씬 영상 전달 방식</legend>
                    <div className="mt-2 grid gap-3 sm:grid-cols-2">
                        <label className="flex cursor-pointer gap-3 rounded-lg border border-white/10 p-3">
                            <input type="radio" name="ae_scene_delivery" value="local" defaultChecked className="mt-1 accent-indigo-500" />
                            <span><strong className="block">로컬 전달 (기본)</strong><span className="mt-1 block text-sm text-gray-400">AE 영상 파일을 같은 PC의 프리미어 워커가 직접 사용합니다.</span></span>
                        </label>
                        <label className="flex cursor-pointer gap-3 rounded-lg border border-white/10 p-3">
                            <input type="radio" name="ae_scene_delivery" value="gcs" className="mt-1 accent-indigo-500" />
                            <span><strong className="block">GCS 업로드</strong><span className="mt-1 block text-sm text-gray-400">씬별 웹 미리보기나 다른 PC의 워커로 인계할 때 사용합니다. 업로드 시간이 추가됩니다.</span></span>
                        </label>
                    </div>
                </fieldset>
                <label className="block">필수·금지 사항<textarea name="requirements" maxLength={1000} rows={3} className={input} placeholder="꼭 넣을 장면, 타깃 시청자, 원하는 분위기, 피할 표현" /></label>
                <details><summary className="cursor-pointer text-gray-300">참고 자막·영상 요약 직접 입력 (선택)</summary><textarea name="transcript" maxLength={40000} rows={6} className={input} placeholder="유튜브 자막을 가져오지 못하는 경우 사용할 자료를 입력하세요." /><p className="mt-2 text-gray-400">URL을 입력하면 승인 후 자막을 수집합니다. 직접 입력한 자료가 있으면 이를 우선 사용합니다.</p></details>
                <button disabled={busy || reading} className="rounded-lg bg-indigo-500 px-5 py-3 font-semibold text-white disabled:opacity-40">{busy ? '등록 중…' : reading ? '이미지 읽는 중…' : '토픽 등록 · 승인 요청'}</button>
            </fieldset>
        </form>
        <div className="rounded-xl border border-white/10 p-5"><div className="flex justify-between items-center"><h2 className="text-lg font-semibold">내 등록 토픽</h2><button type="button" onClick={() => void load()} className="text-indigo-300">새로고침</button></div>
            {!items.length && <p className="py-6 text-gray-400">{loading ? '불러오는 중…' : '등록한 토픽이 없습니다.'}</p>}
            {items.map(item => <article key={item.id} className="border-t border-white/10 py-4 mt-3"><div className="flex justify-between gap-3"><strong>{item.title}</strong><span className="text-indigo-300">{statuses[item.job_status || item.status] || item.status}</span></div><p className="mt-1 text-gray-500">{new Date(item.created_at).toLocaleString()} · AE 씬 전달: {item.ae_scene_delivery === 'gcs' ? 'GCS 업로드' : '로컬 전달'}</p>{item.review_note && <p className="mt-2 whitespace-pre-wrap">검토 의견: {item.review_note}</p>}</article>)}
        </div>
    </section>
}
