'use client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

type Box = [number, number, number, number]
type Speaker = { speaker: string; status: string; face_box?: Box; mouth_box?: Box }
type Scene = {
    number: number
    key: string
    image: any
    rows: { speaker: string; text: string }[]
    result?: { origin: string; speakers: Speaker[] }
    error?: string
    analysisState?: string
    currentScene?: number
    heartbeatAt?: string
}
type Overview = { count: number; completed: number; confirmed: number; failed?: number; pending?: number; scenes: Scene[] }
const empty: Overview = { count: 0, completed: 0, confirmed: 0, scenes: [] }
function names(scene: Scene) {
    return [...new Set(scene.rows.map((r) => r.speaker))]
}
function drafts(scene: Scene): Speaker[] {
    return names(scene).map(
        (speaker) => scene.result?.speakers.find((s) => s.speaker === speaker) || { speaker, status: 'unconfirmed' },
    )
}
function analysisLabel(scene?: Scene) {
    if (!scene) return ''
    if (scene.error) return '자동 분석으로 확정하지 못했습니다. 직접 위치를 지정해 주세요.'
    if (scene.result)
        return scene.result.origin === 'user'
            ? '사용자가 직접 확정한 위치입니다.'
            : '자동 분석된 위치입니다. 이미지와 비교한 뒤 확정하거나 수정해 주세요.'
    if (scene.analysisState === 'queued')
        return '선택한 씬의 자동 분석 대기 중입니다. 기다리지 않고 직접 지정할 수 있습니다.'
    if (scene.analysisState === 'processing') {
        const last = Date.parse(scene.heartbeatAt || '')
        if (!Number.isFinite(last) || Date.now() - last > 120000)
            return '자동 분석 작업기 응답이 지연되고 있습니다. 직접 지정할 수 있습니다.'
        return '자동 분석 중입니다. 기다리지 않고 직접 지정할 수 있습니다.'
    }
    return '화자마다 얼굴과 입 영역을 지정하거나, 실제로 화면에 없는 화자는 화면 밖을 선택해 주세요.'
}
export default function StdSpeakerCoordinates({
    projectId,
    revision,
    headers,
    selectedSceneNumber,
    speakerProgress,
}: {
    projectId: string
    revision: string
    headers: Record<string, string>
    selectedSceneNumber?: number
    speakerProgress?: { total: number; confirmed: number }
}) {
    const [data, setData] = useState<Overview>(empty),
        [error, setError] = useState(''),
        [open, setOpen] = useState(false)
    const [draftKey, setDraftKey] = useState(''),
        [imageSha, setImageSha] = useState(''),
        [imageReload, setImageReload] = useState(0)
    const [number, setNumber] = useState(0),
        [rows, setRows] = useState<Speaker[]>([]),
        [speaker, setSpeaker] = useState(0)
    const [mode, setMode] = useState<'face_box' | 'mouth_box'>('face_box'),
        [image, setImage] = useState(''),
        [loaded, setLoaded] = useState(false)
    const [busy, setBusy] = useState(false),
        [notice, setNotice] = useState(''),
        [drawing, setDrawing] = useState<Box | null>(null)
    const start = useRef<[number, number] | null>(null),
        request = useRef(0),
        saving = useRef(false)
    const scene = data.scenes.find((s) => s.number === number)
    const load = useCallback(
        async (body: any = {}, signal?: AbortSignal) => {
            const seq = ++request.current
            const r = await fetch(`/api/std/projects/${projectId}/speaker-coordinates`, {
                method: 'POST',
                headers,
                body: JSON.stringify(body),
                signal,
            })
            const result = await r.json()
            if (!r.ok) throw new Error(result.error || '위치 확인 정보를 불러오지 못했습니다.')
            if (seq === request.current) {
                setData(result)
                setError('')
            }
            return result as Overview
        },
        [projectId, headers],
    )
    useEffect(() => {
        setData(empty)
        setOpen(false)
        setError('')
    }, [projectId])
    useEffect(() => {
        const controller = new AbortController()
        const refresh = () => {
            if (!saving.current)
                void load({}, controller.signal).catch((e) => {
                    if (!controller.signal.aborted) setError(e.message)
                })
        }
        refresh()
        const timer = setInterval(refresh, 20000)
        return () => {
            controller.abort()
            clearInterval(timer)
            request.current++
        }
    }, [load, revision])
    const choose = (s: Scene) => {
        setDraftKey(s.key)
        setNumber(s.number)
        setRows(drafts(s))
        setSpeaker(0)
        setMode('face_box')
        setNotice('')
        setDrawing(null)
        start.current = null
    }
    useEffect(() => {
        if (!open || !scene?.image) {
            setImage('')
            setLoaded(false)
            return
        }
        const controller = new AbortController()
        let objectUrl = ''
        setImage('')
        setImageSha('')
        setLoaded(false)
        fetch(`/api/std/projects/${projectId}/speaker-coordinates?sceneNumber=${scene.number}`, {
            headers,
            signal: controller.signal,
        })
            .then(async (r) => {
                if (!r.ok) throw new Error('원본 이미지를 불러오지 못했습니다.')
                return r.blob()
            })
            .then(async (blob) => {
                const hash = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
                if (!controller.signal.aborted) {
                    setImageSha(Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, '0')).join(''))
                    objectUrl = URL.createObjectURL(blob)
                    setImage(objectUrl)
                }
            })
            .catch((e) => {
                if (!controller.signal.aborted) setNotice(e.message)
            })
        return () => {
            controller.abort()
            if (objectUrl) URL.revokeObjectURL(objectUrl)
        }
    }, [open, scene?.key, projectId, headers, imageReload])
    const patch = (changes: Partial<Speaker>) =>
        setRows((old) => old.map((r, i) => (i === speaker ? { ...r, ...changes } : r)))
    const point = (e: React.PointerEvent<SVGSVGElement>): [number, number] => {
        const rect = e.currentTarget.getBoundingClientRect()
        return [
            Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
            Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
        ]
    }
    const save = async () => {
        if (!scene || !loaded) return
        setBusy(true)
        saving.current = true
        setNotice('저장 중…')
        request.current++
        try {
            const r = await fetch(`/api/std/projects/${projectId}/speaker-coordinates`, {
                method: 'PATCH',
                headers,
                body: JSON.stringify({
                    sceneNumber: number,
                    sceneKey: draftKey,
                    imageSha256: imageSha,
                    speakers: rows,
                }),
            })
            const result = await r.json()
            if (!r.ok) throw new Error(result.error || '저장하지 못했습니다.')
            request.current++
            setData(result)
            setNotice(`${number}번 씬의 화자 위치를 확정했습니다. AE 작업기를 기다릴 필요가 없습니다.`)
        } catch (e: any) {
            setNotice(e.message)
        } finally {
            setBusy(false)
            saving.current = false
        }
    }
    const current = rows[speaker]
    const button = 'rounded-lg border border-white/20 px-3 py-2 text-sm disabled:opacity-40'
    return (
        <>
            <aside
                aria-label="대사씬 캐릭터 확인"
                className="fixed bottom-4 right-4 z-[60] w-[min(380px,calc(100vw-32px))] rounded-xl border border-cyan-500/40 bg-[#10252d] p-3 text-cyan-200 shadow-lg"
            >
                <h2 className="text-sm font-bold">대사씬 캐릭터 확인</h2>
                <p role="status" className="mt-1 text-xs">
                    {error || `AE 위치 준비 ${data.completed}/${data.count}씬 · 직접 확정 ${data.confirmed}씬`}
                </p>
                <p className="mt-1 text-xs">추가 확인 {data.failed || 0}씬 · 남은 분석 {data.pending ?? Math.max(0, data.count - data.completed)}씬</p>
                {data.completed > 0 && <p className="mt-1 text-xs">완료된 씬의 위치는 저장되어 AE 작업에 사용할 수 있습니다.</p>}
                {speakerProgress && <p className="mt-1 text-xs text-yellow-200">대사 화자 지정 {speakerProgress.confirmed}/{speakerProgress.total}개 자막</p>}
                <div className="mt-2 flex gap-2">
                    <button
                        type="button"
                        disabled={!data.scenes.length}
                        className={`${button} bg-cyan-900`}
                        onClick={() => {
                            const s =
                                data.scenes.find((s) => s.number === selectedSceneNumber) ||
                                data.scenes.find((s) => !s.result) ||
                                data.scenes[0]
                            if (s) {
                                choose(s)
                                setOpen(true)
                            }
                        }}
                    >
                        웹에서 화자 위치 지정
                    </button>
                    <button
                        type="button"
                        className={button}
                        onClick={() => void load().catch((e) => setError(e.message))}
                    >
                        새로고침
                    </button>
                </div>
            </aside>
            {open &&
                scene &&
                createPortal(
                    <div
                        className="fixed inset-0 z-[90] flex items-center justify-center bg-black/80 p-3"
                        onKeyDown={(e) => {
                            if (e.key === 'Escape' && !busy) setOpen(false)
                        }}
                    >
                        <section
                            role="dialog"
                            aria-modal="true"
                            aria-label="화자 얼굴·입 위치 지정"
                            className="max-h-[95vh] w-full max-w-6xl overflow-y-auto rounded-2xl border border-white/20 bg-[#171c24] p-4 text-white shadow-xl"
                        >
                            <div className="flex items-center justify-between gap-3">
                                <h2 className="text-lg font-bold">화자 얼굴·입 위치 지정</h2>
                                <button className={button} disabled={busy} onClick={() => setOpen(false)}>
                                    닫기
                                </button>
                            </div>
                            <div className="my-3 flex flex-wrap items-center gap-3">
                                <label>
                                    씬{' '}
                                    <select
                                        aria-label="확인할 대사씬"
                                        disabled={busy}
                                        value={number}
                                        onChange={(e) => {
                                            const s = data.scenes.find((s) => s.number === Number(e.target.value))
                                            if (s) choose(s)
                                        }}
                                        className="rounded bg-gray-800 p-2"
                                    >
                                        {data.scenes.map((s) => (
                                            <option key={s.number} value={s.number}>
                                                {s.number}번 씬 ·{' '}
                                                {s.result?.origin === 'user'
                                                    ? '직접 확정'
                                                    : s.result
                                                      ? '자동 분석 완료'
                                                      : s.error
                                                        ? '직접 확인 필요'
                                                        : '미확정'}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <label>
                                    화자{' '}
                                    <select
                                        aria-label="위치를 지정할 화자"
                                        disabled={busy}
                                        value={speaker}
                                        onChange={(e) => {
                                            setSpeaker(Number(e.target.value))
                                            setMode('face_box')
                                            setDrawing(null)
                                            start.current = null
                                        }}
                                        className="rounded bg-gray-800 p-2"
                                    >
                                        {rows.map((r, i) => (
                                            <option key={r.speaker} value={i}>
                                                {r.speaker || '이름 미지정'}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <span className="text-xs text-cyan-200">{analysisLabel(scene)}</span>
                            </div>
                            {scene.key !== draftKey && (
                                <p role="alert">
                                    이미지나 화자가 변경됐습니다.{' '}
                                    <button className={button} onClick={() => choose(scene)}>
                                        변경된 씬 다시 불러오기
                                    </button>
                                </p>
                            )}
                            {scene.result && (
                                <button
                                    className={button}
                                    disabled={busy}
                                    onClick={() => {
                                        setRows(drafts(scene))
                                        setNotice('저장된 위치를 불러왔습니다.')
                                    }}
                                >
                                    저장된 위치 불러오기
                                </button>
                            )}
                            <p className="mb-3 text-sm text-gray-300">
                                화자를 선택한 뒤 이미지에서 ① 얼굴 전체, ② 입술과 주변 피부를 차례로 드래그하세요. 화면
                                밖 화자는 입을 움직이지 않습니다. 입이 가려졌거나 식별이 어려우면 확정하지 말고 원본
                                이미지를 수정해 주세요.
                            </p>
                            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
                                <div>
                                    <div className="mb-2 flex flex-wrap gap-2">
                                        <button
                                            disabled={busy}
                                            className={`${button} ${mode === 'face_box' ? 'bg-sky-700' : ''}`}
                                            onClick={() => setMode('face_box')}
                                        >
                                            ① 얼굴 영역 지정
                                        </button>
                                        <button
                                            disabled={busy}
                                            className={`${button} ${mode === 'mouth_box' ? 'bg-pink-700' : ''}`}
                                            onClick={() => setMode('mouth_box')}
                                        >
                                            ② 입 영역 지정
                                        </button>
                                        <button
                                            disabled={busy}
                                            className={button}
                                            onClick={() => setImageReload((n) => n + 1)}
                                        >
                                            이미지 다시 불러오기
                                        </button>
                                        <button
                                            disabled={busy}
                                            className={button}
                                            onClick={() =>
                                                patch({
                                                    status: 'unconfirmed',
                                                    face_box: undefined,
                                                    mouth_box: undefined,
                                                })
                                            }
                                        >
                                            영역 지우기
                                        </button>
                                    </div>
                                    <div className={`relative bg-black ${loaded ? '' : 'min-h-32'}`}>
                                        {image ? (
                                            <img
                                                src={image}
                                                alt={`${number}번 씬 원본 이미지`}
                                                draggable={false}
                                                onLoad={() => setLoaded(true)}
                                                onError={() => setNotice('이미지를 표시하지 못했습니다.')}
                                                className="block h-auto w-full"
                                            />
                                        ) : (
                                            <p className="p-8 text-center">원본 이미지 불러오는 중…</p>
                                        )}
                                        {loaded && (
                                            <svg
                                                aria-label={`${current?.speaker || ''} 얼굴과 입 영역 그리기`}
                                                role="img"
                                                viewBox="0 0 1 1"
                                                preserveAspectRatio="none"
                                                className="absolute inset-0 h-full w-full touch-none"
                                                style={{ cursor: busy ? 'wait' : 'crosshair' }}
                                                onPointerDown={(e) => {
                                                    if (busy) return
                                                    e.currentTarget.setPointerCapture(e.pointerId)
                                                    start.current = point(e)
                                                    setDrawing([
                                                        start.current[0],
                                                        start.current[1],
                                                        start.current[0],
                                                        start.current[1],
                                                    ])
                                                }}
                                                onPointerMove={(e) => {
                                                    if (!start.current) return
                                                    const p = point(e),
                                                        s = start.current
                                                    setDrawing([
                                                        Math.min(s[0], p[0]),
                                                        Math.min(s[1], p[1]),
                                                        Math.max(s[0], p[0]),
                                                        Math.max(s[1], p[1]),
                                                    ])
                                                }}
                                                onPointerCancel={() => {
                                                    start.current = null
                                                    setDrawing(null)
                                                }}
                                                onPointerUp={(e) => {
                                                    const s = start.current
                                                    start.current = null
                                                    setDrawing(null)
                                                    if (!s || busy) return
                                                    const p = point(e),
                                                        b: Box = [
                                                            Math.min(s[0], p[0]),
                                                            Math.min(s[1], p[1]),
                                                            Math.max(s[0], p[0]),
                                                            Math.max(s[1], p[1]),
                                                        ]
                                                    if (b[2] - b[0] < 0.002 || b[3] - b[1] < 0.002) return
                                                    patch({ [mode]: b, status: 'visible' })
                                                    if (mode === 'face_box') setMode('mouth_box')
                                                }}
                                            >
                                                {rows.flatMap((r, i) =>
                                                    (['face_box', 'mouth_box'] as const).map((k) => {
                                                        const b = r[k]
                                                        return r.status === 'visible' && b ? (
                                                            <rect
                                                                key={`${i}-${k}`}
                                                                x={b[0]}
                                                                y={b[1]}
                                                                width={b[2] - b[0]}
                                                                height={b[3] - b[1]}
                                                                fill="none"
                                                                stroke={k === 'face_box' ? '#38bdf8' : '#f472b6'}
                                                                strokeWidth={i === speaker ? 0.003 : 0.0015}
                                                                strokeDasharray={i === speaker ? undefined : '0.005'}
                                                            />
                                                        ) : null
                                                    }),
                                                )}
                                                {drawing && (
                                                    <rect
                                                        x={drawing[0]}
                                                        y={drawing[1]}
                                                        width={drawing[2] - drawing[0]}
                                                        height={drawing[3] - drawing[1]}
                                                        fill="none"
                                                        stroke="#fff"
                                                        strokeWidth=".003"
                                                    />
                                                )}
                                            </svg>
                                        )}
                                    </div>
                                </div>
                                <div className="space-y-3">
                                    <p className="font-bold">{current?.speaker}</p>
                                    <button
                                        className={`${button} w-full ${current?.status === 'offscreen' ? 'bg-cyan-800' : ''}`}
                                        disabled={busy || !loaded}
                                        onClick={() =>
                                            patch({ status: 'offscreen', face_box: undefined, mouth_box: undefined })
                                        }
                                    >
                                        이 화자는 화면 밖에 있음
                                    </button>
                                    <p className="text-xs text-gray-300">
                                        {current?.status === 'offscreen'
                                            ? '화면 밖으로 선택됨'
                                            : current?.face_box && current?.mouth_box
                                              ? '얼굴·입 영역 지정됨'
                                              : '얼굴·입 영역을 지정해 주세요.'}
                                    </p>
                                    <div className="max-h-44 overflow-auto text-sm text-gray-300">
                                        {scene.rows
                                            .filter((r) => r.speaker === current?.speaker)
                                            .map((r, i) => (
                                                <p className="mb-2" key={i}>
                                                    {r.text}
                                                </p>
                                            ))}
                                    </div>
                                    <button
                                        className={`${button} w-full`}
                                        disabled={busy || !scene.image}
                                        onClick={async () => {
                                            setBusy(true)
                                            try {
                                                await load({ action: 'analyze', sceneNumber: number })
                                                setNotice(
                                                    '선택한 씬만 자동 분석을 요청했습니다. 직접 지정은 바로 가능합니다.',
                                                )
                                            } catch (e: any) {
                                                setNotice(e.message)
                                            } finally {
                                                setBusy(false)
                                            }
                                        }}
                                    >
                                        선택 씬 자동 분석 (선택 사항)
                                    </button>
                                    <p className="text-xs text-gray-400">
                                        자동 분석은 연결된 분석 작업기가 필요합니다. 직접 확정은 작업기 없이 저장됩니다.
                                    </p>
                                </div>
                            </div>
                            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                                <p role="status" className="text-sm text-cyan-200">
                                    {notice}
                                </p>
                                <button
                                    className={`${button} bg-emerald-700 font-bold`}
                                    disabled={
                                        busy ||
                                        !loaded ||
                                        !imageSha ||
                                        scene.key !== draftKey ||
                                        rows.some((r) => r.status !== 'offscreen' && (!r.face_box || !r.mouth_box))
                                    }
                                    onClick={() => void save()}
                                >
                                    이 씬 화자 위치 확정
                                </button>
                            </div>
                        </section>
                    </div>,
                    document.body,
                )}
        </>
    )
}
