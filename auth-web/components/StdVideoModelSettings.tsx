'use client'
import { useEffect, useState } from 'react'
import type { VideoModel, VideoModelSettings } from '@/lib/stdVideoModels'

export default function StdVideoModelSettings({ headers }: { headers: HeadersInit }) {
    const [catalog, setCatalog] = useState<VideoModelSettings>({ models: [], active_id: null })
    const [form, setForm] = useState({ id: '', name: '', model: '', endpoint: '', api_key: '' })
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
            if (body) { setForm({ id: '', name: '', model: '', endpoint: '', api_key: '' }); setMessage('설정이 저장되었습니다.') }
        } catch (error: any) { setMessage(error.message) } finally { setBusy(false) }
    }
    useEffect(() => { void request() }, [headers]) // Account headers change when the signed-in account changes.
    function edit(item: VideoModel) { setForm({ id: item.id, name: item.name, model: item.model, endpoint: item.endpoint, api_key: '' }) }
    return <section className="rounded-2xl border border-white/10 bg-[#1c2027] p-5 space-y-4 text-sm text-white">
        <h3 className="font-bold">영상 생성 모델 · API 설정</h3>
        <p className="text-xs text-gray-400">서비스별 모델과 API를 등록한 후 사용할 모델을 적용하세요. 현재는 설정 저장 단계이며, 실제 영상 생성 요청과 비용은 발생하지 않습니다. 제공자별 생성·결과 조회 연결은 별도 구현이 필요합니다.</p>
        {catalog.models.map(item => <div key={item.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-white/10 p-3">
            <div className="min-w-0 flex-1"><strong>{item.name}</strong><p className="text-xs text-gray-400 break-all">{item.model} · {item.endpoint} · {item.has_key ? '키 등록됨' : '키 없음'}</p></div>
            <button disabled={busy} onClick={() => edit(item)}>수정</button>
            <button disabled={busy} onClick={() => void request({ action: 'delete', id: item.id })}>삭제</button>
            <button className="rounded bg-blue-600 px-3 py-2 disabled:opacity-50" disabled={busy || catalog.active_id === item.id} onClick={() => void request({ action: 'apply', id: item.id })}>{catalog.active_id === item.id ? '적용 중' : '선택 / 적용'}</button>
        </div>)}
        {loaded && !catalog.models.length && <p className="text-gray-400">등록된 모델이 없습니다.</p>}
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={event => { event.preventDefault(); void request({ action: 'save', model: { ...form, id: form.id || crypto.randomUUID() }, api_key: form.api_key }) }}>
            {([['name', '표시 이름', '예: 제작용 영상 모델'], ['model', '모델 ID', '서비스에서 안내한 모델 ID'], ['endpoint', 'API 주소', 'https://api.example.com/video'], ['api_key', 'API 키', form.id ? '비워두면 기존 키 유지' : 'API 키 입력']] as const).map(([key, label, placeholder]) => <label key={key} className="space-y-1"><span>{label}</span><input className="block w-full rounded-lg border border-white/15 bg-black/30 p-2" name={`video-provider-${key}`} type={key === 'api_key' ? 'password' : key === 'endpoint' ? 'url' : 'text'} autoComplete={key === 'api_key' ? 'new-password' : 'off'} data-lpignore="true" data-1p-ignore="true" required={key !== 'api_key' || !form.id} value={form[key]} placeholder={placeholder} onChange={event => setForm({ ...form, [key]: event.target.value })} /></label>)}
            <p className="text-xs text-gray-400 sm:col-span-2">API 키는 서버에 암호화하여 저장하며 다시 표시하지 않습니다. 주소에 키를 넣지 마세요.</p>
            <button disabled={busy || !loaded} className="rounded-lg bg-blue-600 p-2 disabled:opacity-50">{busy ? '처리 중…' : form.id ? '모델 수정 저장' : '모델 등록'}</button>
            {form.id && <button type="button" onClick={() => setForm({ id: '', name: '', model: '', endpoint: '', api_key: '' })}>수정 취소</button>}
        </form>
        <p role="status" className="text-xs text-blue-300">{message}</p>
        {!loaded && !busy && <button onClick={() => void request()}>다시 불러오기</button>}
    </section>
}
