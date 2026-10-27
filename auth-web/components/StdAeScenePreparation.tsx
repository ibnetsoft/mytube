'use client'

import { useCallback, useEffect, useState } from 'react'
import { AE_SCENE_EFFECTS } from '../lib/stdAeSceneEffects'

type Scene = {
    number: number; title: string; source: { id: string; file_name: string } | null
    preparation: { id: string; enabled: boolean; state: string; direction_text: string; requested_effects?: string[]; error: string; progress: string; plan: any } | null
}
type Data = { editable: boolean; scenes: Scene[] }
const statusText: Record<string, string> = { queued: '준비 대기', processing: '레이어·연출 준비 중', prepared: '제출 준비 완료', failed: '수정 필요', stale: '다시 준비 필요', disabled: '사용 안 함' }
const EFFECT_PRESETS = [
    { label: '전투 타격', effects: ['impact_shake', 'impact_flash', 'shock_ring', 'speedline_burst', 'particle_burst'], direction: '타격 순간에 짧은 카메라 흔들림과 섬광, 충격파·집중선·파티클을 넣고 바로 다음 컷으로 연결.' },
    { label: '검기·오라', effects: ['focus_glow', 'energy_trail', 'light_sweep', 'warm_dust_motes'], direction: '인물과 무기 주변의 기존 빛 방향을 유지하며 짧은 에너지 궤적과 발광을 강조.' },
    { label: '충돌·파괴', effects: ['impact_flash', 'shock_ring', 'debris_burst', 'speedline_burst'], direction: '충돌 지점에서만 섬광·충격파·파편을 분출하고 인물 원화나 배경 구도는 바꾸지 않음.' },
    { label: '분위기·빛', effects: ['atmospheric_haze', 'warm_dust_motes', 'focus_glow', 'light_sweep', 'subtle_vignette'], direction: '원화의 광원 방향과 색을 유지하며 안개·먼지·빛 변화로 깊이만 더함.' },
] as const

export default function StdAeScenePreparation({ projectId, headers, onPreparedScenesChange, ui = (s: string) => s }: {
    projectId: string; headers: Record<string, string>; onPreparedScenesChange?: (numbers: number[]) => void; ui?: (text: string) => string
}) {
    const [open, setOpen] = useState(false), [data, setData] = useState<Data | null>(null)
    const [number, setNumber] = useState(0), [drafts, setDrafts] = useState<Record<number, string>>({})
    const [effectDrafts, setEffectDrafts] = useState<Record<number, string[]>>({})
    const [busy, setBusy] = useState(''), [error, setError] = useState('')
    const headerKey = JSON.stringify(headers), endpoint = `/api/std/projects/${projectId}/ae-scene`
    const read = useCallback(async (signal?: AbortSignal) => {
        const response = await fetch(endpoint, { headers: JSON.parse(headerKey), signal, cache: 'no-store' })
        const result = await response.json()
        if (!response.ok) throw new Error(result.error || '연출 상태를 불러오지 못했습니다.')
        setData(result)
    }, [endpoint, headerKey])
    useEffect(() => {
        if (!open) return
        const abort = new AbortController()
        const refresh = () => { if (!document.hidden) void read(abort.signal).catch(e => { if (!abort.signal.aborted) setError(e.message) }) }
        void read(abort.signal).catch(e => { if (!abort.signal.aborted) setError(e.message) })
        const timer = setInterval(refresh, 10000)
        return () => { clearInterval(timer); abort.abort() }
    }, [open, read])
    useEffect(() => {
        if (data) onPreparedScenesChange?.(data.scenes.filter(s => s.preparation?.enabled && s.preparation.state === 'prepared').map(s => s.number))
    }, [data, onPreparedScenesChange])
    const scene = data?.scenes.find(s => s.number === number) || data?.scenes[0]
    const direction = scene ? drafts[scene.number] ?? scene.preparation?.direction_text ?? '' : ''
    const effects = scene ? effectDrafts[scene.number] ?? scene.preparation?.requested_effects ?? [] : []
    const locked = !data?.editable || Boolean(busy)
    const applyPreset = (preset: typeof EFFECT_PRESETS[number]) => {
        if (!scene) return
        setEffectDrafts(d => ({ ...d, [scene.number]: [...new Set([...effects, ...preset.effects])].sort() }))
        if (!direction.trim()) setDrafts(d => ({ ...d, [scene.number]: preset.direction }))
    }
    const json = async (url: string, body: unknown) => {
        const response = await fetch(url, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        const result = await response.json()
        if (!response.ok) throw new Error(result.error || '요청을 처리하지 못했습니다.')
        return result
    }
    const upload = async (file: File | undefined) => {
        if (!file || !scene) return
        setError('')
        if (!/\.(psd|psb)$/i.test(file.name)) { setError('PSD 또는 PSB 파일을 선택해 주세요.'); return }
        if (file.size > 1024 * 1024 * 1024) { setError('씬별 PSD는 1GB 이하로 준비해 주세요.'); return }
        setBusy('PSD 업로드 중…')
        try {
            const spec = { scene_number: scene.number, asset_type: 'original', file_name: file.name, mime_type: 'image/vnd.adobe.photoshop', file_size: file.size }
            const init = await json(`/api/std/projects/${projectId}/assets/init`, spec)
            const put = await fetch(init.storage_upload_url, { method: 'PUT', headers: { 'Content-Type': spec.mime_type }, body: file })
            if (!put.ok) throw new Error('PSD 업로드에 실패했습니다. 다시 시도해 주세요.')
            await json(`/api/std/projects/${projectId}/assets/complete`, { ...spec, storage_provider: 'gcs', storage_bucket: init.storage_bucket, storage_path: init.storage_path })
            await read()
        } catch (e: any) { setError(e.message) }
        finally { setBusy('') }
    }
    const request = async (action: 'prepare' | 'disable') => {
        if (!scene) return
        setBusy('요청 중…'); setError('')
        try {
            const result = await json(endpoint, { action, scene_number: scene.number, source_asset_id: scene.source?.id, direction_text: direction, requested_effects: effects })
            setData(result)
        } catch (e: any) { setError(e.message) }
        finally { setBusy('') }
    }
    return <details className="mx-5 rounded-xl border border-cyan-500/25 bg-[#141b25] p-4" onToggle={e => setOpen(e.currentTarget.open)}>
        <summary className="cursor-pointer text-sm font-semibold text-cyan-200">{ui('PSD로 AE 장면 연출')}</summary>
        {open && <div className="mt-3 space-y-3">
            <p className="text-xs leading-relaxed text-gray-300">{ui('씬별 PSD와 원하는 연출을 준비합니다. 기존 영상 업로드와 음성 생성 순서는 그대로이며, 제출 후 최종 음성에 맞춰 AE가 카메라·부위 움직임·빛을 합성합니다.')}</p>
            <label className="block text-xs text-gray-300">{ui('작업할 씬')}
                <select value={scene?.number || ''} disabled={Boolean(busy)} onChange={e => setNumber(Number(e.target.value))} className="ml-2 max-w-full rounded bg-[#242d3b] p-2 text-white">
                    {(data?.scenes || []).map(s => <option key={s.number} value={s.number}>{s.number} · {s.title || ui('씬')}{s.preparation?.enabled ? ` · ${ui(statusText[s.preparation.state] || s.preparation.state)}` : ''}</option>)}
                </select>
            </label>
            {scene && <>
                <label className="block text-xs text-gray-300">{ui('원본 PSD / PSB')}
                    <input type="file" accept=".psd,.psb" disabled={locked} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; void upload(file) }} className="mt-1 block w-full text-xs file:mr-3 file:rounded file:border-0 file:bg-cyan-950 file:px-3 file:py-2 file:text-cyan-100 disabled:opacity-50" />
                </label>
                {scene.source && <p className="break-all text-xs text-cyan-200">{scene.source.file_name}</p>}
                <label className="block text-xs text-gray-300">{ui('원하는 연출')}
                    <textarea value={direction} maxLength={4000} disabled={locked} rows={3} onChange={e => setDrafts(d => ({ ...d, [scene.number]: e.target.value }))}
                        placeholder={ui('예: 머리카락 끝만 약하게 흔들고, 얼굴로 천천히 접근. 빛은 왼쪽에서 유지하고 다음 씬의 오른쪽을 보는 시선으로 연결.')}
                        className="mt-1 w-full rounded border border-white/15 bg-[#0f141d] p-2 text-sm text-white disabled:opacity-50" />
                </label>
                <fieldset disabled={locked} className="space-y-2">
                    <legend className="text-xs text-gray-300">{ui('AE 추가 효과')}</legend>
                    <div className="flex flex-wrap gap-2">{EFFECT_PRESETS.map(preset => <button key={preset.label} type="button" disabled={locked} onClick={() => applyPreset(preset)} className="rounded border border-cyan-500/40 px-2 py-1 text-xs text-cyan-100 disabled:opacity-40">{ui(preset.label)}</button>)}</div>
                    <div className="flex flex-wrap gap-3">{AE_SCENE_EFFECTS.filter(effect=>effect.id!=='fireflies').map(effect => <label key={effect.id} className="flex items-center gap-1 text-xs text-gray-200">
                        <input type="checkbox" checked={effects.includes(effect.id)} onChange={e => setEffectDrafts(d => ({ ...d,
                            [scene.number]: e.target.checked ? [...effects, effect.id] : effects.filter(id => id !== effect.id),
                        }))} />{ui(effect.label)}
                    </label>)}</div>
                    <p className="text-xs text-gray-400">{ui('프리셋은 선택 항목과 빈 연출 문구를 채웁니다. 위치·강도·시점은 원하는 연출에 적어 주세요. 준비를 다시 요청하면 검수 후 반영됩니다. 열 왜곡은 분리된 배경이나 소품에만 적용합니다.')}</p>
                </fieldset>
                <p className="text-xs text-gray-400">{ui('원화와 레이어를 검사하고 필요한 빈 배경만 정지 이미지로 보완합니다. 분리되지 않은 부위나 추가 그림이 필요한 동작은 수정 필요로 표시됩니다.')}</p>
                <p className="text-xs text-amber-200">{ui('현재 PSD 연출은 카메라·레이어 움직임·조명·컷 전환과 선택한 추가 효과를 지원합니다. 같은 씬에 별도로 선택한 입모양·눈깜빡임 작업이 있으면 함께 제출할 수 없습니다.')}</p>
                <div className="flex flex-wrap items-center gap-2">
                    <button type="button" disabled={locked || !scene.source || !direction.trim() || ['queued', 'processing'].includes(scene.preparation?.state || '')}
                        onClick={() => void request('prepare')} className="rounded bg-cyan-700 px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">{ui(busy || '레이어·연출 준비')}</button>
                    {scene.preparation?.enabled && <button type="button" disabled={locked} onClick={() => void request('disable')} className="rounded border border-white/20 px-3 py-2 text-xs text-gray-300 disabled:opacity-40">{ui('이 씬의 PSD 연출 사용 안 함')}</button>}
                    <span role="status" className="text-xs text-cyan-200">{ui(scene.preparation?.progress || statusText[scene.preparation?.state || ''] || '')}</span>
                </div>
                {scene.preparation?.error && <p role="alert" className="text-xs text-amber-300">{scene.preparation.error}</p>}
                {scene.preparation?.plan && <div className="rounded bg-black/20 p-3 text-xs leading-relaxed text-gray-300">
                    <p className="font-semibold text-cyan-100">{ui('준비된 연출')}</p>
                    <p>{scene.preparation.plan.intent}</p>
                    <p>{ui('카메라 지점')} {scene.preparation.plan.camera?.length || 0} · {ui('레이어')} {scene.preparation.plan.layers?.length || 0} · {ui('빛 효과')} {scene.preparation.plan.lights?.length || 0}</p>
                    <p>{ui('추가 효과')}: {(scene.preparation.plan.effects || []).map((effect: any) => ui(AE_SCENE_EFFECTS.find(item => item.id === effect.type)?.label || effect.type)).join(' · ') || ui('없음')}</p>
                    {scene.preparation.plan.continuity?.entry && <p>{ui('시작 상태')}: {scene.preparation.plan.continuity.entry}</p>}
                    {scene.preparation.plan.continuity?.exit && <p>{ui('끝 상태')}: {scene.preparation.plan.continuity.exit}</p>}
                </div>}
                {!data?.editable && <p className="text-xs text-gray-400">{ui('제출된 프로젝트는 저장된 PSD와 연출로 작업합니다.')}</p>}
            </>}
            {!data && !error && <p role="status" className="text-xs text-gray-400">{ui('불러오는 중…')}</p>}
            {error && <p role="alert" className="text-xs text-red-300">{error}</p>}
        </div>}
    </details>
}
