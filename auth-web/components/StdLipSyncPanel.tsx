'use client'
import { useEffect, useState } from 'react'

export default function StdLipSyncPanel({ projectId, headers, beforeSave }: {
    projectId: string; headers: Record<string, string>; beforeSave: () => Promise<any>
}) {
    const [open, setOpen] = useState(false), [data, setData] = useState<any>(null)
    const [error, setError] = useState(''), [busy, setBusy] = useState(false)
    const [points, setPoints] = useState<Record<string, any>>({}), [speaker, setSpeaker] = useState<Record<string, string>>({})
    const endpoint = `/api/std/projects/${encodeURIComponent(projectId)}/lipsync`
    const key = JSON.stringify(headers)
    useEffect(() => {
        if (!open) return
        let live = true
        const controller = new AbortController()
        const read = async () => {
            try {
                const r = await fetch(endpoint, { headers: JSON.parse(key), signal: controller.signal }), d = await r.json()
                if (live) { if (!r.ok) setError(d.error); else setData(d) }
            } catch (e: any) { if (live) setError(e.message) }
        }
        void read()
        const timer = setInterval(read, 10000)
        return () => { live = false; controller.abort(); clearInterval(timer) }
    }, [open, endpoint, key])
    const act = async (scene: any, action: string) => {
        setBusy(true); setError('')
        try {
            await beforeSave()
            const r = await fetch(endpoint, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({ scene_number: scene.number, fingerprint: scene.fingerprint, action, points: points[scene.number] || scene.points }) })
            const d = await r.json()
            if (!r.ok) throw new Error(d.error)
            const status = await fetch(endpoint, { headers }), latest = await status.json()
            if (!status.ok) throw new Error(latest.error)
            setData(latest)
        } catch (e: any) { setError(e.message) } finally { setBusy(false) }
    }
    return <div className="rounded border border-cyan-500/30 p-2 text-xs">
        <button type="button" onClick={() => setOpen(!open)} className="rounded bg-cyan-800 px-3 py-2">대사 영상 · 립싱크</button>
        {open && <div className="mt-3 max-h-[60vh] space-y-3 overflow-auto">
            <p>저장+TTS 완료 → 말할 인물 지정 → 대사 영상 생성 → 립싱크 검수 → AE → AE 검수 → 최종 렌더링</p>
            <p className="text-gray-400">일레븐랩스 음성을 그대로 사용합니다. 대사만 영상으로 만들며, 내레이션 구간은 인물 이미지로 유지합니다. 생성 시 외부 서비스 비용이 발생합니다.</p>
            {data && !data.configured && <p className="text-amber-300">관리자 설정 → API Keys에서 Hedra API Key를 등록해 주세요.</p>}
            {data?.preparationError && <p className="text-amber-300">{data.preparationError}</p>}
            {data?.scenes?.length === 0 && !data.preparationError && <p>인물 대사로 표시된 자막이 없습니다.</p>}
            {(data?.scenes || []).map((s: any) => {
                const selected = speaker[s.number] || s.speakers[0]
                const xy = (points[s.number] || s.points)?.[selected]
                return <div key={s.number} className="space-y-2 rounded bg-black/20 p-2">
                    <p>씬 {s.number} · {s.status}{s.aeState ? ` · AE ${s.aeState}` : ''}{s.aeReviewed ? ' · AE 검수 완료' : ''}</p>
                    <label>말할 인물 <select value={selected} onChange={e => setSpeaker({ ...speaker, [s.number]: e.target.value })} className="bg-gray-800">
                        {s.speakers.map((name: string) => <option key={name}>{name}</option>)}
                    </select></label>
                    {s.imageUrl && <div className="relative">
                        <img src={s.imageUrl} alt={`씬 ${s.number}: 말할 인물의 얼굴을 클릭하세요`} className="w-full cursor-crosshair" onClick={e => {
                            if (s.status !== 'not_started') return
                            const box = e.currentTarget.getBoundingClientRect()
                            setPoints({ ...points, [s.number]: { ...(points[s.number] || s.points), [selected]: [(e.clientX - box.left) / box.width, (e.clientY - box.top) / box.height] } })
                        }} />
                        {xy && <span className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-500 px-2" style={{ left: `${xy[0] * 100}%`, top: `${xy[1] * 100}%` }}>{selected}</span>}
                    </div>}
                    <p>각 화자를 선택하고 이미지에서 해당 얼굴을 클릭하세요.</p>
                    {s.status === 'not_started' && <div className="flex gap-2">{[0, 1].map(axis => <label key={axis}>{selected} 얼굴 {axis === 0 ? 'X' : 'Y'}
                        <input type="number" min="0" max="1" step="0.01" value={xy?.[axis] ?? ''} className="ml-1 w-20 bg-gray-800" onChange={e => {
                            const value = Number(e.target.value), next = [...(xy || [.5, .5])]
                            if (!Number.isFinite(value) || value < 0 || value > 1) return
                            next[axis] = value
                            setPoints({ ...points, [s.number]: { ...(points[s.number] || s.points), [selected]: next } })
                        }} /></label>)}</div>}
                    {s.status === 'not_started' && <button type="button" disabled={busy || !data.configured} onClick={() => void act(s, 'generate')} className="rounded bg-cyan-700 px-3 py-2 disabled:opacity-50">대사 영상 생성</button>}
                    {s.status === 'failed' && <button type="button" disabled={busy || !data.configured} onClick={() => void act(s, 'retry')} className="rounded bg-amber-800 px-3 py-2">실패한 생성 재시도 · 추가 비용 가능</button>}
                    {s.videoUrl && <video src={s.videoUrl} controls className="w-full" />}
                    {s.status === 'review_pending' && <><p className="text-gray-400">검수 후 기존 AE 연출 계획을 이 영상에 적용합니다. 입모양과 영상 속도는 유지합니다.</p><pre className="whitespace-pre-wrap text-gray-400">{s.aeDirection}</pre><button type="button" disabled={busy} onClick={() => void act(s, 'review_lipsync')} className="rounded bg-emerald-800 px-3 py-2">입모양 확인 완료 · AE 진행</button></>}
                    {s.aeUrl && !s.aeReviewed && <><video src={s.aeUrl} controls className="w-full" /><button type="button" disabled={busy} onClick={() => void act(s, 'review_ae')} className="rounded bg-emerald-800 px-3 py-2">AE 영상 확인 완료</button></>}
                    {s.error && <p className="text-amber-300">{s.error}</p>}
                </div>
            })}
        </div>}
        {error && <p role="alert" className="mt-2 text-amber-300">{error}</p>}
    </div>
}
