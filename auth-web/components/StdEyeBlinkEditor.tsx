'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type Box = [number, number, number, number]
type Scene = { number: number; imageId: string; characters: string[]; plan?: any }

export default function StdEyeBlinkEditor({ projectId, headers, selectedSceneNumber, locale = 'ko' }: {
    projectId: string; headers: Record<string, string>; selectedSceneNumber?: number; locale?: string
}) {
    const th = locale === 'th', text = (ko: string, thai: string) => th ? thai : ko
    const api = `/api/std/projects/${projectId}/eye-blink`
    const [open, setOpen] = useState(false), [scenes, setScenes] = useState<Scene[]>([]), [number, setNumber] = useState(0)
    const [character, setCharacter] = useState(''), [left, setLeft] = useState<Box | null>(null), [right, setRight] = useState<Box | null>(null)
    const [mode, setMode] = useState<'left' | 'right'>('left'), [interval, setIntervalValue] = useState(4)
    const [image, setImage] = useState(''), [dimensions, setDimensions] = useState<[number, number]>([16, 9])
    const [sha, setSha] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState('')
    const start = useRef<[number, number] | null>(null), scene = scenes.find(row => row.number === number)
    const button = 'rounded-md border border-white/20 px-3 py-2 text-sm disabled:opacity-40'
    async function refresh() { const r = await fetch(api, { headers }); const d = await r.json(); if (!r.ok) throw new Error(d.error); setScenes(d.scenes); return d.scenes as Scene[] }
    function choose(row: Scene) {
        setNumber(row.number); setCharacter(row.plan?.character || row.characters[0] || '')
        setLeft(row.plan?.left_eye_box || null); setRight(row.plan?.right_eye_box || null); setIntervalValue(row.plan?.interval_seconds || 4)
        setMode('left'); setNotice('')
    }
    useEffect(() => {
        if (!open || !number) return
        const controller = new AbortController(); let url = ''
        setImage(''); setSha('')
        void fetch(`${api}?image=${number}`, { headers, signal: controller.signal }).then(async response => {
            if (!response.ok) throw new Error(text('이미지를 불러오지 못했습니다.', 'โหลดภาพไม่สำเร็จ'))
            const blob = await response.blob(), hash = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
            if (!controller.signal.aborted) {
                url = URL.createObjectURL(blob)
                const probe = new globalThis.Image()
                probe.onload = () => { if (!controller.signal.aborted) setDimensions([probe.naturalWidth || 16, probe.naturalHeight || 9]) }
                probe.src = url
                setImage(url); setSha(Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join(''))
            }
        }).catch(error => { if (!controller.signal.aborted) setNotice(error.message) })
        return () => { controller.abort(); if (url) URL.revokeObjectURL(url) }
    }, [open, number, scene?.imageId, api, headers])
    const point = (event: React.PointerEvent<SVGSVGElement>): [number, number] => { const box = event.currentTarget.getBoundingClientRect(); return [Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)), Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))] }
    async function save() {
        if (!scene || !left || !right || !sha) return
        setBusy(true); setNotice('')
        try {
            const response = await fetch(api, { method: 'POST', headers, body: JSON.stringify({ sceneNumber: number, imageId: scene.imageId, imageSha256: sha, character, leftEyeBox: left, rightEyeBox: right, intervalSeconds: interval }) })
            const data = await response.json(); if (!response.ok) throw new Error(data.error)
            const items = await refresh(), current = items.find(row => row.number === number); if (current) choose(current)
            setNotice(text('눈 깜빡임 작업을 저장했습니다.', 'บันทึกงานกะพริบตาแล้ว'))
        } catch (error: any) { setNotice(error.message) } finally { setBusy(false) }
    }
    return <>
        <button type="button" className="w-max max-w-full flex-none rounded-md border border-white/20 bg-violet-900 px-2 py-1 text-xs" onClick={async () => {
            try { const items = await refresh(); const selected = items.find(row => row.number === selectedSceneNumber) || items[0]; if (!selected) throw new Error(text('19번 이후 정지 이미지가 필요합니다.', 'ต้องมีภาพนิ่งตั้งแต่ฉากที่ 19 เป็นต้นไป')); choose(selected); setOpen(true) } catch (error: any) { setNotice(error.message) }
        }}>{text('눈 깜빡임 지정', 'กำหนดการกะพริบตา')}</button>
        {!open && notice && <span className="text-xs">{notice}</span>}
        {open && scene && createPortal(<div className="fixed inset-0 z-[190] flex items-center justify-center bg-black/80 p-3"><section role="dialog" aria-modal="true" className="max-h-[96vh] w-full max-w-6xl overflow-auto rounded-xl bg-[#171c24] p-4 text-white">
            <header className="flex items-center justify-between"><h2 className="text-xl font-bold">{text('캐릭터 눈 깜빡임 지정', 'กำหนดการกะพริบตาของตัวละคร')}</h2><button className={button} disabled={busy} onClick={() => setOpen(false)}>{text('닫기', 'ปิด')}</button></header>
            <div className="my-3 flex flex-wrap gap-3"><label>{text('씬', 'ฉาก')} <select className="rounded bg-gray-800 p-2" value={number} onChange={event => { const row = scenes.find(item => item.number === Number(event.target.value)); if (row) choose(row) }}>{scenes.map(row => <option key={row.number} value={row.number}>{row.number}</option>)}</select></label>
                <label>{text('캐릭터', 'ตัวละคร')} <input list="blink-characters" className="rounded bg-gray-800 p-2" value={character} onChange={event => setCharacter(event.target.value)} /><datalist id="blink-characters">{scene.characters.map(name => <option key={name} value={name} />)}</datalist></label>
                <label>{text('깜빡임 간격', 'ช่วงเวลากะพริบ')} <input className="w-20 rounded bg-gray-800 p-2" type="number" min={2} max={12} step={.5} value={interval} onChange={event => setIntervalValue(Number(event.target.value))} /> {text('초', 'วินาที')}</label></div>
            <p className="mb-2 text-sm text-gray-300">{text('캐릭터를 선택하고 왼쪽 눈과 오른쪽 눈을 각각 작게 드래그하세요. 지정한 원본 이미지에서만 사용됩니다.', 'เลือกตัวละครแล้วลากกรอบเล็ก ๆ รอบตาซ้ายและตาขวา ระบบจะใช้เฉพาะกับภาพต้นฉบับนี้')}</p>
            <div className="mb-2 flex gap-2"><button className={`${button} ${mode === 'left' ? 'bg-sky-700' : ''}`} onClick={() => setMode('left')}>{text('① 왼쪽 눈', '① ตาซ้าย')}</button><button className={`${button} ${mode === 'right' ? 'bg-pink-700' : ''}`} onClick={() => setMode('right')}>{text('② 오른쪽 눈', '② ตาขวา')}</button></div>
            {image ? <svg viewBox={`0 0 ${dimensions[0]} ${dimensions[1]}`} className="w-full touch-none bg-black" onPointerDown={event => { start.current = point(event); event.currentTarget.setPointerCapture(event.pointerId) }} onPointerUp={event => { if (!start.current) return; const a = start.current, b = point(event); start.current = null; const box: Box = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]; if (mode === 'left') { setLeft(box); setMode('right') } else setRight(box) }}><image href={image} width={dimensions[0]} height={dimensions[1]} />{left && <rect x={left[0] * dimensions[0]} y={left[1] * dimensions[1]} width={(left[2] - left[0]) * dimensions[0]} height={(left[3] - left[1]) * dimensions[1]} fill="none" stroke="#38bdf8" strokeWidth={Math.max(2, dimensions[0] / 500)} />}{right && <rect x={right[0] * dimensions[0]} y={right[1] * dimensions[1]} width={(right[2] - right[0]) * dimensions[0]} height={(right[3] - right[1]) * dimensions[1]} fill="none" stroke="#f472b6" strokeWidth={Math.max(2, dimensions[0] / 500)} />}</svg> : <div className="p-20 text-center">{text('이미지 불러오는 중…', 'กำลังโหลดภาพ…')}</div>}
            <div className="mt-3 flex items-center gap-3"><button className="rounded bg-emerald-800 px-4 py-2 disabled:opacity-40" disabled={busy || !character || !left || !right || !sha} onClick={() => void save()}>{text('눈 깜빡임 저장', 'บันทึกการกะพริบตา')}</button><span role="status" className="text-cyan-200">{notice}</span></div>
        </section></div>, document.body)}
    </>
}
