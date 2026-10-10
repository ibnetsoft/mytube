'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type Box = [number, number, number, number]
type Locale = 'ko' | 'en' | 'vi' | 'th'
type CharacterOption = { name: string; labels?: Partial<Record<Locale, string>> }
type Scene = { number: number; imageId: string; characters: CharacterOption[]; plan?: any }

const copies = {
    ko: {
        launcher: '눈 깜빡임 지정', title: '캐릭터 눈 깜빡임 지정', close: '닫기', scene: '씬', character: '캐릭터',
        interval: '깜빡임 간격', seconds: '초', noCharacters: '선택 가능한 캐릭터 없음',
        instruction: '왼쪽 눈과 오른쪽 눈을 각각 작게 드래그하세요. 캐릭터 이름은 선택 사항이며, 지정한 원본 이미지에서만 사용됩니다.',
        leftEye: '① 왼쪽 눈', rightEye: '② 오른쪽 눈', loading: '이미지 불러오는 중…', save: '눈 깜빡임 저장',
        saved: '눈 깜빡임 작업을 저장했습니다.', imageLoadFailed: '이미지를 불러오지 못했습니다.',
        stillRequired: '19번 이후 정지 이미지가 필요합니다.', projectMissing: '프로젝트를 찾을 수 없습니다.',
        imageChanged: '원본 이미지가 변경됐습니다. 다시 불러와 주세요.', imageMissing: '원본 이미지를 찾지 못했습니다.',
        characterTooLong: '캐릭터 이름은 100자 이내로 입력해 주세요.', eyesRequired: '왼쪽 눈과 오른쪽 눈의 작은 영역을 각각 지정해 주세요.',
        eyesOverlap: '왼쪽 눈과 오른쪽 눈 영역이 겹칠 수 없습니다.', intervalInvalid: '눈 깜빡임 간격은 2~12초로 설정해 주세요.',
    },
    en: {
        launcher: 'Set eye blink', title: 'Set character eye blink', close: 'Close', scene: 'Scene', character: 'Character',
        interval: 'Blink interval', seconds: 'sec', noCharacters: 'No characters available',
        instruction: 'Drag a small box around each eye. The character name is optional, and the setting applies only to this source image.',
        leftEye: '① Left eye', rightEye: '② Right eye', loading: 'Loading image…', save: 'Save eye blink',
        saved: 'Eye blink settings saved.', imageLoadFailed: 'Could not load the image.',
        stillRequired: 'A still image from scene 19 onward is required.', projectMissing: 'Project not found.',
        imageChanged: 'The source image changed. Please load it again.', imageMissing: 'The source image could not be found.',
        characterTooLong: 'Character names must be 100 characters or fewer.', eyesRequired: 'Draw a small area around both the left and right eye.',
        eyesOverlap: 'The left and right eye areas cannot overlap.', intervalInvalid: 'Set the blink interval between 2 and 12 seconds.',
    },
    vi: {
        launcher: 'Đặt chớp mắt', title: 'Đặt chớp mắt cho nhân vật', close: 'Đóng', scene: 'Cảnh', character: 'Nhân vật',
        interval: 'Chu kỳ chớp mắt', seconds: 'giây', noCharacters: 'Không có nhân vật để chọn',
        instruction: 'Kéo một khung nhỏ quanh từng mắt trái và phải. Tên nhân vật là tùy chọn và thiết lập chỉ áp dụng cho ảnh gốc này.',
        leftEye: '① Mắt trái', rightEye: '② Mắt phải', loading: 'Đang tải ảnh…', save: 'Lưu chớp mắt',
        saved: 'Đã lưu thiết lập chớp mắt.', imageLoadFailed: 'Không thể tải ảnh.',
        stillRequired: 'Cần có ảnh tĩnh từ cảnh 19 trở đi.', projectMissing: 'Không tìm thấy dự án.',
        imageChanged: 'Ảnh gốc đã thay đổi. Vui lòng tải lại.', imageMissing: 'Không tìm thấy ảnh gốc.',
        characterTooLong: 'Tên nhân vật phải có tối đa 100 ký tự.', eyesRequired: 'Hãy chọn vùng nhỏ cho cả mắt trái và mắt phải.',
        eyesOverlap: 'Vùng mắt trái và mắt phải không được chồng lên nhau.', intervalInvalid: 'Hãy đặt chu kỳ chớp mắt từ 2 đến 12 giây.',
    },
    th: {
        launcher: 'กำหนดการกะพริบตา', title: 'กำหนดการกะพริบตาของตัวละคร', close: 'ปิด', scene: 'ฉาก', character: 'ตัวละคร',
        interval: 'ช่วงเวลากะพริบ', seconds: 'วินาที', noCharacters: 'ไม่มีตัวละครให้เลือก',
        instruction: 'ลากกรอบเล็ก ๆ รอบตาซ้ายและตาขวา ชื่อตัวละครเป็นข้อมูลเสริม และระบบจะใช้เฉพาะกับภาพต้นฉบับนี้',
        leftEye: '① ตาซ้าย', rightEye: '② ตาขวา', loading: 'กำลังโหลดภาพ…', save: 'บันทึกการกะพริบตา',
        saved: 'บันทึกงานกะพริบตาแล้ว', imageLoadFailed: 'โหลดภาพไม่สำเร็จ',
        stillRequired: 'ต้องมีภาพนิ่งตั้งแต่ฉากที่ 19 เป็นต้นไป', projectMissing: 'ไม่พบโปรเจกต์',
        imageChanged: 'ภาพต้นฉบับมีการเปลี่ยนแปลง โปรดโหลดใหม่', imageMissing: 'ไม่พบภาพต้นฉบับ',
        characterTooLong: 'ชื่อตัวละครต้องไม่เกิน 100 ตัวอักษร', eyesRequired: 'โปรดกำหนดพื้นที่เล็ก ๆ ของตาซ้ายและตาขวา',
        eyesOverlap: 'พื้นที่ตาซ้ายและตาขวาต้องไม่ซ้อนกัน', intervalInvalid: 'ตั้งช่วงเวลากะพริบตาระหว่าง 2 ถึง 12 วินาที',
    },
} as const

export default function StdEyeBlinkEditor({ projectId, headers, selectedSceneNumber, locale = 'ko' }: {
    projectId: string; headers: Record<string, string>; selectedSceneNumber?: number; locale?: string
}) {
    const activeLocale: Locale = locale === 'en' || locale === 'vi' || locale === 'th' ? locale : 'ko'
    const copy = copies[activeLocale]
    const api = `/api/std/projects/${projectId}/eye-blink`
    const [open, setOpen] = useState(false), [scenes, setScenes] = useState<Scene[]>([]), [number, setNumber] = useState(0)
    const [character, setCharacter] = useState(''), [left, setLeft] = useState<Box | null>(null), [right, setRight] = useState<Box | null>(null)
    const [mode, setMode] = useState<'left' | 'right'>('left'), [interval, setIntervalValue] = useState(4)
    const [image, setImage] = useState(''), [dimensions, setDimensions] = useState<[number, number]>([16, 9])
    const [sha, setSha] = useState(''), [busy, setBusy] = useState(false), [notice, setNotice] = useState('')
    const start = useRef<[number, number] | null>(null), scene = scenes.find(row => row.number === number)
    const button = 'rounded-md border border-white/20 px-3 py-2 text-sm disabled:opacity-40'
    const characterLabel = (option: CharacterOption) => {
        const localized = String(option.labels?.[activeLocale] || '').trim()
        return localized && localized !== option.name ? `${option.name} (${localized})` : option.name
    }
    const localizedError = (message: string) => {
        const keys = ['projectMissing', 'imageChanged', 'imageMissing', 'characterTooLong', 'eyesRequired', 'eyesOverlap', 'intervalInvalid'] as const
        const korean = copies.ko
        const key = keys.find(item => message === korean[item])
        return key ? copy[key] : message
    }
    async function refresh() {
        const response = await fetch(api, { headers })
        const data = await response.json()
        if (!response.ok) throw new Error(localizedError(data.error))
        setScenes(data.scenes)
        return data.scenes as Scene[]
    }
    function choose(row: Scene) {
        setNumber(row.number); setCharacter(row.plan?.character || row.characters[0]?.name || '')
        setLeft(row.plan?.left_eye_box || null); setRight(row.plan?.right_eye_box || null); setIntervalValue(row.plan?.interval_seconds || 4)
        setMode('left'); setNotice('')
    }
    useEffect(() => {
        if (!open || !number) return
        const controller = new AbortController(); let url = ''
        setImage(''); setSha('')
        void fetch(`${api}?image=${number}`, { headers, signal: controller.signal }).then(async response => {
            if (!response.ok) throw new Error(copy.imageLoadFailed)
            const serverSha = response.headers.get('X-Air-Image-Sha256') || ''
            const blob = await response.blob()
            if (!controller.signal.aborted) {
                url = URL.createObjectURL(blob)
                const probe = new globalThis.Image()
                probe.onload = () => { if (!controller.signal.aborted) setDimensions([probe.naturalWidth || 16, probe.naturalHeight || 9]) }
                probe.src = url
                setImage(url); setSha(serverSha)
            }
        }).catch(error => { if (!controller.signal.aborted) setNotice(error.message) })
        return () => { controller.abort(); if (url) URL.revokeObjectURL(url) }
    }, [open, number, scene?.imageId, api, headers, copy.imageLoadFailed])
    const point = (event: React.PointerEvent<SVGSVGElement>): [number, number] => { const box = event.currentTarget.getBoundingClientRect(); return [Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)), Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))] }
    async function save() {
        if (!scene || !left || !right) return
        setBusy(true); setNotice('')
        try {
            const response = await fetch(api, { method: 'POST', headers, body: JSON.stringify({ sceneNumber: number, imageId: scene.imageId, imageSha256: sha, character, leftEyeBox: left, rightEyeBox: right, intervalSeconds: interval }) })
            const data = await response.json(); if (!response.ok) throw new Error(localizedError(data.error))
            const items = await refresh(), current = items.find(row => row.number === number); if (current) choose(current)
            setNotice(copy.saved)
        } catch (error: any) { setNotice(localizedError(error.message)) } finally { setBusy(false) }
    }
    return <>
        <button type="button" className="w-max max-w-full flex-none rounded-md border border-white/20 bg-violet-900 px-2 py-1 text-xs" onClick={async () => {
            try { const items = await refresh(); const selected = items.find(row => row.number === selectedSceneNumber) || items[0]; if (!selected) throw new Error(copy.stillRequired); choose(selected); setOpen(true) } catch (error: any) { setNotice(localizedError(error.message)) }
        }}>{copy.launcher}</button>
        {!open && notice && <span className="text-xs">{notice}</span>}
        {open && scene && createPortal(<div className="fixed inset-0 z-[190] flex items-center justify-center bg-black/80 p-3"><section role="dialog" aria-modal="true" className="max-h-[96vh] w-full max-w-6xl overflow-auto rounded-xl bg-[#171c24] p-4 text-white">
            <header className="flex items-center justify-between"><h2 className="text-xl font-bold">{copy.title}</h2><button className={button} disabled={busy} onClick={() => setOpen(false)}>{copy.close}</button></header>
            <div className="my-3 flex flex-wrap gap-3"><label>{copy.scene} <select className="rounded bg-gray-800 p-2" value={number} onChange={event => { const row = scenes.find(item => item.number === Number(event.target.value)); if (row) choose(row) }}>{scenes.map(row => <option key={row.number} value={row.number}>{row.number}</option>)}</select></label>
                <label>{copy.character} <select className="min-w-44 rounded bg-gray-800 p-2" value={character} onChange={event => setCharacter(event.target.value)}><option value="">{copy.noCharacters}</option>{scene.characters.map(option => <option key={option.name} value={option.name}>{characterLabel(option)}</option>)}</select></label>
                <label>{copy.interval} <input className="w-20 rounded bg-gray-800 p-2" type="number" min={2} max={12} step={.5} value={interval} onChange={event => setIntervalValue(Number(event.target.value))} /> {copy.seconds}</label></div>
            <p className="mb-2 text-sm text-gray-300">{copy.instruction}</p>
            <div className="mb-2 flex gap-2"><button className={`${button} ${mode === 'left' ? 'bg-sky-700' : ''}`} onClick={() => setMode('left')}>{copy.leftEye}</button><button className={`${button} ${mode === 'right' ? 'bg-pink-700' : ''}`} onClick={() => setMode('right')}>{copy.rightEye}</button></div>
            {image ? <svg viewBox={`0 0 ${dimensions[0]} ${dimensions[1]}`} className="mx-auto w-3/5 max-w-full touch-none bg-black" onPointerDown={event => { start.current = point(event); event.currentTarget.setPointerCapture(event.pointerId) }} onPointerUp={event => { if (!start.current) return; const a = start.current, b = point(event); start.current = null; const box: Box = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]; if (mode === 'left') { setLeft(box); setMode('right') } else setRight(box) }}><image href={image} width={dimensions[0]} height={dimensions[1]} />{left && <rect x={left[0] * dimensions[0]} y={left[1] * dimensions[1]} width={(left[2] - left[0]) * dimensions[0]} height={(left[3] - left[1]) * dimensions[1]} fill="none" stroke="#38bdf8" strokeWidth={Math.max(2, dimensions[0] / 500)} />}{right && <rect x={right[0] * dimensions[0]} y={right[1] * dimensions[1]} width={(right[2] - right[0]) * dimensions[0]} height={(right[3] - right[1]) * dimensions[1]} fill="none" stroke="#f472b6" strokeWidth={Math.max(2, dimensions[0] / 500)} />}</svg> : <div className="p-20 text-center">{copy.loading}</div>}
            <div className="mt-3 flex items-center gap-3"><button className="rounded bg-emerald-800 px-4 py-2 disabled:opacity-40" disabled={busy || !left || !right || !image} onClick={() => void save()}>{copy.save}</button><span role="status" className="text-cyan-200">{notice}</span></div>
        </section></div>, document.body)}
    </>
}
