'use client'
import { useEffect, useState } from 'react'
import type { VideoModel, VideoModelSettings } from '@/lib/stdVideoModels'
const blank=()=>({ id:'',name:'',model:'',endpoint:'',api_key:'',provider:'fal',image_field:'image_url',duration_field:'duration',duration_type:'string',extra_input:'{}' })

export default function StdVideoModelSettings({ headers }: { headers: HeadersInit }) {
    const [catalog, setCatalog] = useState<VideoModelSettings>({ models: [], active_id: null })
    const [form, setForm] = useState(blank)
    const [busy, setBusy] = useState(false)
    const [message, setMessage] = useState('')
    const [loaded, setLoaded] = useState(false)
    async function request(body?: object) {
        setBusy(true); setMessage('')
        try {
            const response = await fetch('/api/std/video-models', { method: body ? 'POST' : 'GET', headers: { ...Object.fromEntries(new Headers(headers)), 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) })
            const data = await response.json()
            if (!response.ok) throw new Error(data.error || '설정을 처리하지 못했습니다.')
            setCatalog(data); setLoaded(true)
            if (body) { setForm(blank()); setMessage('설정이 저장되었습니다.') }
        } catch (error: any) { setMessage(error.message) } finally { setBusy(false) }
    }
    useEffect(() => { void request() }, [headers]) // Account headers change when the signed-in account changes.
    function edit(item: VideoModel) { setForm({ ...blank(),...item,provider:item.provider||'unconfigured',api_key:'',extra_input:JSON.stringify(item.extra_input||{},null,2) }) }
    return <section className="rounded-2xl border border-white/10 bg-[#1c2027] p-5 space-y-4 text-sm text-white">
        <h3 className="font-bold">영상 생성 모델 · API 설정</h3>
        <p className="text-xs text-gray-400">혼합 자동 제작에서 사용할 모델입니다. 제출할 때 선택한 모델을 고정하고, Codex가 정한 짧은 구간에만 호출합니다. AE 중심 모드는 이 API를 호출하지 않습니다. 설정 저장 자체로는 생성 비용이 발생하지 않습니다.</p>
        {catalog.models.map(item => <div key={item.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 p-3">
            <div className="min-w-0 flex-1"><strong>{item.name}</strong><p className="text-xs text-gray-400 break-all">{item.model} · {item.endpoint} · {item.has_key ? '키 등록됨' : '키 없음'}</p></div>
            <button disabled={busy} onClick={() => edit(item)}>수정</button>
            <button disabled={busy} onClick={() => void request({ action: 'delete', id: item.id })}>삭제</button>
            <button className="rounded bg-blue-600 px-3 py-2 disabled:opacity-50" disabled={busy || catalog.active_id === item.id} onClick={() => void request({ action: 'apply', id: item.id })}>{catalog.active_id === item.id ? '적용 중' : '선택 / 적용'}</button>
        </div>)}
        {loaded && !catalog.models.length && <p className="text-gray-400">등록된 모델이 없습니다.</p>}
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={event => { event.preventDefault(); try { const {api_key,extra_input,...model}=form; void request({ action:'save',model:{...model,id:form.id||crypto.randomUUID(),extra_input:JSON.parse(extra_input)},api_key }) } catch { setMessage('추가 입력 JSON을 확인해 주세요.') } }}>
            <label>API 방식<select aria-label="영상 API 방식" className="block w-full rounded bg-black/30 p-2" value={form.provider} onChange={e=>{const provider=e.target.value;setForm({...form,provider,image_field:provider==='fal'?'image_url':'image',endpoint:provider==='fal'?`https://queue.fal.run/${form.model}`:`https://api.replicate.com/v1/models/${form.model}/predictions`})}}><option value="fal">fal 큐 API</option><option value="replicate">Replicate Predictions API</option><option value="unconfigured" disabled>기존 설정 · API 방식 지정 필요</option></select></label>
            {([['name', '표시 이름', '예: 제작용 영상 모델'], ['model', '모델 ID', '서비스에서 안내한 모델 ID'], ['endpoint', 'API 주소', 'https://api.example.com/video'], ['api_key', 'API 키', form.id ? '비워두면 기존 키 유지' : 'API 키 입력']] as const).map(([key, label, placeholder]) => <label key={key} className="space-y-1"><span>{label}</span><input className="block w-full rounded-lg border border-white/15 bg-black/30 p-2" name={`video-provider-${key}`} type={key === 'api_key' ? 'password' : key === 'endpoint' ? 'url' : 'text'} autoComplete={key === 'api_key' ? 'new-password' : 'off'} data-lpignore="true" data-1p-ignore="true" required={key !== 'api_key' || !form.id} value={form[key]} placeholder={placeholder} onChange={event => setForm({ ...form, [key]: event.target.value })} /></label>)}
            <p className="text-xs text-gray-400 sm:col-span-2">API 키는 서버에 암호화하여 저장하며 다시 표시하지 않습니다. 주소에 키를 넣지 마세요.</p>
            <details className="sm:col-span-2 space-y-2"><summary>모델별 입력 형식</summary><p className="text-xs text-gray-400">모델 문서에 맞게 이미지·길이 필드와 추가 옵션을 지정하세요. prompt와 이미지·길이는 Codex 연출로 입력됩니다.</p>{(['image_field','duration_field'] as const).map(key=><label key={key} className="block">{key==='image_field'?'원본 이미지 필드':'길이 필드'}<input className="block w-full rounded bg-black/30 p-2" value={form[key]} onChange={e=>setForm({...form,[key]:e.target.value})}/></label>)}<label>길이 값 형식<select value={form.duration_type} onChange={e=>setForm({...form,duration_type:e.target.value})}><option value="string">문자열 (예: "5")</option><option value="number">숫자 (예: 5)</option></select></label><label className="block">추가 입력 JSON<textarea className="block w-full rounded bg-black/30 p-2" rows={3} value={form.extra_input} onChange={e=>setForm({...form,extra_input:e.target.value})}/></label></details>
            <button disabled={busy || !loaded} className="rounded-lg bg-blue-600 p-2 disabled:opacity-50">{busy ? '처리 중…' : form.id ? '모델 수정 저장' : '모델 등록'}</button>
            {form.id && <button type="button" onClick={() => setForm(blank())}>수정 취소</button>}
        </form>
        <p role="status" className="text-xs text-blue-300">{message}</p>
        {!loaded && !busy && <button onClick={() => void request()}>다시 불러오기</button>}
    </section>
}
