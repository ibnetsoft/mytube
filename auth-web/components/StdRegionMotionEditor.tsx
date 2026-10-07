'use client'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
    motionPhase,
    parseRegionMotionCommand,
    regionMotionLabels,
    validateRegionMotions,
    type MotionPoint,
    type RegionMotion,
} from '@/lib/stdRegionMotion'
type Scene = {
    number: number
    imageId: string
    duration: number
    subtitles: { id: string; text: string; start: number; end: number }[]
    plan?: any
}
export default function StdRegionMotionEditor({
    projectId,
    headers,
    selectedSceneNumber,
    onApplied,
}: {
    projectId: string
    headers: Record<string, string>
    selectedSceneNumber?: number
    onApplied?: () => void
}) {
    const [open, setOpen] = useState(false),
        [scenes, setScenes] = useState<Scene[]>([]),
        [number, setNumber] = useState(0)
    const [regions, setRegions] = useState<RegionMotion[]>([]),
        [selected, setSelected] = useState(0),
        [tool, setTool] = useState<'rectangle' | 'polygon' | 'anchor'>(
            'rectangle',
        )
    const [image, setImage] = useState(''),
        [sha, setSha] = useState(''),
        [size, setSize] = useState<[number, number]>([1000, 600])
    const [points, setPoints] = useState<MotionPoint[]>([]),
        [notice, setNotice] = useState(''),
        [busy, setBusy] = useState(false),
        [command, setCommand] = useState('')
    const [playing, setPlaying] = useState(false),
        [time, setTime] = useState(0),
        [video, setVideo] = useState(''),
        [dirty, setDirty] = useState(false)
    const drag = useRef<MotionPoint | null>(null),
        scene = scenes.find((s) => s.number === number),
        region = regions[selected]
    const api = `/api/std/projects/${projectId}/region-motion`
    const button =
        'rounded border border-white/20 px-3 py-2 text-sm disabled:opacity-40'
    const input = 'rounded bg-gray-800 p-2 text-white w-full'
    async function refresh() {
        const r = await fetch(api, { headers })
        const data = await r.json()
        if (!r.ok) throw new Error(data.error)
        setScenes(data.scenes)
        return data.scenes as Scene[]
    }
    function choose(s: Scene) {
        setNumber(s.number)
        setRegions(
            s.plan?.input?.image?.id === s.imageId ? s.plan.input.regions : [],
        )
        setSelected(0)
        setPoints([])
        setVideo('')
        setNotice('')
        setDirty(false)
        setPlaying(false)
        setTime(0)
    }
    useEffect(() => {
        if (!open) return
        const timer = setInterval(
            () => void refresh().catch((e) => setNotice(e.message)),
            5000,
        )
        return () => clearInterval(timer)
    }, [open, api, headers]) // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => {
        if (!open || !number) return
        const abort = new AbortController()
        let url = ''
        setImage('')
        setSha('')
        void fetch(`${api}?image=${number}`, { headers, signal: abort.signal })
            .then(async (r) => {
                if (!r.ok) throw new Error('이미지를 불러오지 못했습니다.')
                const blob = await r.blob()
                const hash = await crypto.subtle.digest(
                    'SHA-256',
                    await blob.arrayBuffer(),
                )
                if (abort.signal.aborted) return
                url = URL.createObjectURL(blob)
                setImage(url)
                setSha(
                    Array.from(new Uint8Array(hash), (b) =>
                        b.toString(16).padStart(2, '0'),
                    ).join(''),
                )
            })
            .catch((e) => {
                if (!abort.signal.aborted) setNotice(e.message)
            })
        return () => {
            abort.abort()
            if (url) URL.revokeObjectURL(url)
        }
    }, [open, number, api, headers, scene?.imageId])
    useEffect(() => {
        if (!playing || !scene) return
        const begin = performance.now() - time * 1000
        let frame = 0
        const tick = (now: number) => {
            setTime(((now - begin) / 1000) % scene.duration)
            frame = requestAnimationFrame(tick)
        }
        frame = requestAnimationFrame(tick)
        return () => cancelAnimationFrame(frame)
    }, [playing, scene?.duration]) // eslint-disable-line react-hooks/exhaustive-deps
    function patch(value: Partial<RegionMotion>) {
        setRegions((rows) =>
            rows.map((r, i) => (i === selected ? { ...r, ...value } : r)),
        )
        setDirty(true)
        setVideo('')
    }
    function point(e: React.PointerEvent<SVGSVGElement>): MotionPoint {
        const b = e.currentTarget.getBoundingClientRect()
        return [
            Math.max(0, Math.min(1, (e.clientX - b.left) / b.width)),
            Math.max(0, Math.min(1, (e.clientY - b.top) / b.height)),
        ]
    }
    function finish(polygon: MotionPoint[]) {
        if (!scene || polygon.length < 3) return
        if (regions.length >= 8) {
            setNotice('영역은 최대 8개입니다.')
            return
        }
        const xs = polygon.map((p) => p[0]),
            ys = polygon.map((p) => p[1])
        const item: RegionMotion = {
            id: crypto.randomUUID(),
            name: `영역 ${regions.length + 1}`,
            polygon,
            anchor: [
                (Math.min(...xs) + Math.max(...xs)) / 2,
                (Math.min(...ys) + Math.max(...ys)) / 2,
            ],
            action: 'horizontal',
            amplitude: 2,
            period: Math.min(2, scene.duration),
            cycles: 1,
            subtitleId: scene.subtitles[0]?.id || '',
            start: 0,
        }
        setRegions([...regions, item])
        setSelected(regions.length)
        setPoints([])
        setDirty(true)
        setVideo('')
    }
    async function submit(action: 'save' | 'render' | 'apply') {
        if (!scene) return
        setBusy(true)
        setNotice('')
        setPlaying(false)
        try {
            const body =
                action === 'apply'
                    ? { action, sceneNumber: number, planId: scene.plan?.id }
                    : {
                          action,
                          sceneNumber: number,
                          imageId: scene.imageId,
                          imageSha256: sha,
                          regions:
                              action === 'save' && !regions.length
                                  ? []
                                  : validateRegionMotions(regions, scene),
                      }
            const response = await fetch(api, {
                method: 'POST',
                headers,
                body: JSON.stringify(body),
            })
            const result = await response.json()
            if (!response.ok) throw new Error(result.error)
            await refresh()
            setDirty(false)
            setNotice(
                action === 'apply'
                    ? '이 씬에 AE 영상을 적용했습니다.'
                    : action === 'render'
                      ? 'AE 렌더를 요청했습니다. 완료되면 결과를 확인해 주세요.'
                      : '영역과 동작 설정을 저장했습니다.',
            )
            if (action === 'apply') onApplied?.()
        } catch (e: any) {
            setNotice(e.message)
        } finally {
            setBusy(false)
        }
    }
    const coords = (polygon: MotionPoint[]) =>
        polygon.map((p) => `${p[0] * size[0]},${p[1] * size[1]}`).join(' ')
    const states: Record<string, string> = {
        draft: '설정 저장됨',
        queued: 'AE 작업 대기',
        processing: 'AE 렌더 중',
        ready: 'AE 결과 준비됨',
        failed: '렌더 실패',
        obsolete: '설정 변경됨 · 다시 렌더 필요',
    }
    return (
        <>
            <button
                type="button"
                className={`${button} mt-2 w-full bg-indigo-900`}
                onClick={async () => {
                    try {
                        const items = await refresh()
                        const s =
                            items.find(
                                (s) => s.number === selectedSceneNumber,
                            ) || items[0]
                        if (!s)
                            throw new Error('먼저 씬 이미지를 준비해 주세요.')
                        choose(s)
                        setOpen(true)
                    } catch (e: any) {
                        setNotice(e.message)
                    }
                }}
            >
                영역 동작 지정 · AE
            </button>
            {!open && notice && <p role="status">{notice}</p>}
            {open &&
                createPortal(
                    <div className="fixed inset-0 z-[180] flex items-center justify-center bg-black/80 p-3">
                        <section
                            role="dialog"
                            aria-modal="true"
                            aria-label="영역 동작 지정"
                            className="max-h-[96vh] w-full max-w-7xl overflow-auto rounded-xl bg-[#171c24] p-4 text-white"
                        >
                            <header className="flex justify-between">
                                <h2 className="text-xl font-bold">
                                    영역 동작 지정
                                </h2>
                                <button
                                    className={button}
                                    disabled={busy}
                                    onClick={() => {
                                        setOpen(false)
                                        setPlaying(false)
                                    }}
                                >
                                    닫기
                                </button>
                            </header>
                            <div className="my-3 flex flex-wrap items-center gap-3">
                                <label>
                                    씬{' '}
                                    <select
                                        aria-label="동작 씬"
                                        disabled={busy}
                                        className={input}
                                        value={number}
                                        onChange={(e) => {
                                            const s = scenes.find(
                                                (s) =>
                                                    s.number ===
                                                    Number(e.target.value),
                                            )
                                            if (s) choose(s)
                                        }}
                                    >
                                        {scenes.map((s) => (
                                            <option
                                                key={s.number}
                                                value={s.number}
                                            >
                                                {s.number}번 씬 ·{' '}
                                                {s.duration.toFixed(1)}초
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <span>
                                    {states[scene?.plan?.state] ||
                                        '영역과 동작을 지정해 주세요.'}
                                    {dirty ? ' · 저장 전 변경 있음' : ''}
                                </span>
                            </div>
                            <p className="mb-3 text-sm text-gray-300">
                                움직일 부위를 외곽선으로 지정하고 고정점을
                                찍으세요. 팔 흔들기는 고정점을 중심으로
                                회전합니다. 관절을 구부리는 동작은 아직 지원하지
                                않습니다.
                            </p>
                            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
                                <div>
                                    <div className="mb-2 flex flex-wrap gap-2">
                                        {(
                                            [
                                                'rectangle',
                                                'polygon',
                                                'anchor',
                                            ] as const
                                        ).map((t) => (
                                            <button
                                                key={t}
                                                disabled={
                                                    busy ||
                                                    playing ||
                                                    !sha ||
                                                    (t === 'anchor' && !region)
                                                }
                                                className={`${button} ${tool === t ? 'bg-cyan-800' : ''}`}
                                                onClick={() => {
                                                    setTool(t)
                                                    setPoints([])
                                                }}
                                            >
                                                {
                                                    {
                                                        rectangle:
                                                            '사각형 영역',
                                                        polygon:
                                                            '외곽선 점 찍기',
                                                        anchor: '고정점 지정',
                                                    }[t]
                                                }
                                            </button>
                                        ))}
                                        {tool === 'polygon' && (
                                            <button
                                                className={button}
                                                disabled={
                                                    points.length < 3 || playing
                                                }
                                                onClick={() => finish(points)}
                                            >
                                                외곽선 완료
                                            </button>
                                        )}
                                    </div>
                                    {image ? (
                                        <svg
                                            role="img"
                                            aria-label="움직일 영역과 고정점 지정"
                                            viewBox={`0 0 ${size[0]} ${size[1]}`}
                                            className="w-full touch-none bg-gray-700"
                                            onPointerDown={(e) => {
                                                if (playing || busy) return
                                                const p = point(e)
                                                if (tool === 'anchor') {
                                                    patch({ anchor: p })
                                                    return
                                                }
                                                if (tool === 'polygon') {
                                                    setPoints(
                                                        [...points, p].slice(
                                                            0,
                                                            32,
                                                        ),
                                                    )
                                                    return
                                                }
                                                drag.current = p
                                                e.currentTarget.setPointerCapture(
                                                    e.pointerId,
                                                )
                                            }}
                                            onPointerUp={(e) => {
                                                if (
                                                    !drag.current ||
                                                    playing ||
                                                    busy
                                                )
                                                    return
                                                const a = drag.current,
                                                    b = point(e)
                                                drag.current = null
                                                if (
                                                    Math.abs(a[0] - b[0]) <
                                                        0.01 ||
                                                    Math.abs(a[1] - b[1]) < 0.01
                                                )
                                                    return
                                                finish([
                                                    [
                                                        Math.min(a[0], b[0]),
                                                        Math.min(a[1], b[1]),
                                                    ],
                                                    [
                                                        Math.max(a[0], b[0]),
                                                        Math.min(a[1], b[1]),
                                                    ],
                                                    [
                                                        Math.max(a[0], b[0]),
                                                        Math.max(a[1], b[1]),
                                                    ],
                                                    [
                                                        Math.min(a[0], b[0]),
                                                        Math.max(a[1], b[1]),
                                                    ],
                                                ])
                                            }}
                                            onPointerCancel={() => {
                                                drag.current = null
                                            }}
                                        >
                                            <defs>
                                                <mask id="motion-base-mask">
                                                    <rect
                                                        width={size[0]}
                                                        height={size[1]}
                                                        fill="white"
                                                    />
                                                    {regions.map((r) => (
                                                        <polygon
                                                            key={r.id}
                                                            points={coords(
                                                                r.polygon,
                                                            )}
                                                            fill="black"
                                                        />
                                                    ))}
                                                </mask>
                                                {regions.map((r) => (
                                                    <clipPath
                                                        key={r.id}
                                                        id={`region-${r.id}`}
                                                    >
                                                        <polygon
                                                            points={coords(
                                                                r.polygon,
                                                            )}
                                                        />
                                                    </clipPath>
                                                ))}
                                            </defs>
                                            <image
                                                href={image}
                                                width={size[0]}
                                                height={size[1]}
                                                mask={
                                                    playing || time > 0
                                                        ? 'url(#motion-base-mask)'
                                                        : undefined
                                                }
                                            />
                                            {regions.map((r, i) => {
                                                const v =
                                                        motionPhase(r, time) *
                                                        r.amplitude,
                                                    a = [
                                                        r.anchor[0] * size[0],
                                                        r.anchor[1] * size[1],
                                                    ],
                                                    transform =
                                                        r.action ===
                                                        'horizontal'
                                                            ? `translate(${(v * size[0]) / 100} 0)`
                                                            : r.action ===
                                                                'vertical'
                                                              ? `translate(0 ${(v * size[1]) / 100})`
                                                              : r.action ===
                                                                  'rotate'
                                                                ? `rotate(${v} ${a[0]} ${a[1]})`
                                                                : `translate(${a[0]} ${a[1]}) scale(${1 + v / 100}) translate(${-a[0]} ${-a[1]})`
                                                return (
                                                    <g key={r.id}>
                                                        <g
                                                            transform={
                                                                transform
                                                            }
                                                        >
                                                            <image
                                                                href={image}
                                                                width={size[0]}
                                                                height={size[1]}
                                                                clipPath={`url(#region-${r.id})`}
                                                            />
                                                        </g>
                                                        {!playing && (
                                                            <>
                                                                <polygon
                                                                    points={coords(
                                                                        r.polygon,
                                                                    )}
                                                                    fill="transparent"
                                                                    stroke={
                                                                        i ===
                                                                        selected
                                                                            ? '#22d3ee'
                                                                            : '#9ca3af'
                                                                    }
                                                                    strokeWidth={
                                                                        size[0] /
                                                                        400
                                                                    }
                                                                    onPointerDown={(
                                                                        e,
                                                                    ) => {
                                                                        if (
                                                                            tool ===
                                                                                'anchor' ||
                                                                            tool ===
                                                                                'polygon'
                                                                        )
                                                                            return
                                                                        e.stopPropagation()
                                                                        setSelected(
                                                                            i,
                                                                        )
                                                                    }}
                                                                />
                                                                <circle
                                                                    cx={a[0]}
                                                                    cy={a[1]}
                                                                    r={
                                                                        size[0] /
                                                                        150
                                                                    }
                                                                    fill="#f472b6"
                                                                />
                                                            </>
                                                        )}
                                                    </g>
                                                )
                                            })}
                                            <polyline
                                                points={coords(points)}
                                                fill="none"
                                                stroke="#fbbf24"
                                                strokeWidth={size[0] / 400}
                                            />
                                        </svg>
                                    ) : (
                                        <p>이미지 불러오는 중…</p>
                                    )}
                                    {image && (
                                        <img
                                            className="hidden"
                                            src={image}
                                            alt=""
                                            onLoad={(e) =>
                                                setSize([
                                                    e.currentTarget
                                                        .naturalWidth,
                                                    e.currentTarget
                                                        .naturalHeight,
                                                ])
                                            }
                                        />
                                    )}
                                    <div className="mt-3 flex items-center gap-2">
                                        <button
                                            className={button}
                                            disabled={
                                                !regions.length ||
                                                !scene?.duration
                                            }
                                            onClick={() => setPlaying(!playing)}
                                        >
                                            {playing
                                                ? '미리보기 정지'
                                                : '동작 미리보기'}
                                        </button>
                                        <input
                                            aria-label="동작 미리보기 시간"
                                            className="flex-1"
                                            type="range"
                                            min="0"
                                            max={scene?.duration || 1}
                                            step="0.01"
                                            value={time}
                                            onChange={(e) => {
                                                setPlaying(false)
                                                setTime(Number(e.target.value))
                                            }}
                                        />
                                        <span>{time.toFixed(1)}초</span>
                                    </div>
                                    <p className="mt-2 text-xs text-gray-400">
                                        회색 빈 영역은 움직인 뒤 드러나는
                                        부분입니다. 배경 보정 상태는 실제 AE
                                        결과에서 확인하세요.
                                    </p>
                                    {video && (
                                        <video
                                            className="mt-3 w-full"
                                            src={video}
                                            controls
                                        />
                                    )}
                                </div>
                                <div className="space-y-3">
                                    <label>
                                        영역 선택
                                        <select
                                            aria-label="동작 영역"
                                            className={input}
                                            value={selected}
                                            onChange={(e) =>
                                                setSelected(
                                                    Number(e.target.value),
                                                )
                                            }
                                        >
                                            {regions.map((r, i) => (
                                                <option key={r.id} value={i}>
                                                    {r.name}
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                    {region && (
                                        <>
                                            <label>
                                                영역 이름
                                                <input
                                                    aria-label="영역 이름"
                                                    className={input}
                                                    value={region.name}
                                                    onChange={(e) =>
                                                        patch({
                                                            name: e.target
                                                                .value,
                                                        })
                                                    }
                                                />
                                            </label>
                                            <label>
                                                동작
                                                <select
                                                    aria-label="동작 종류"
                                                    className={input}
                                                    value={region.action}
                                                    onChange={(e) =>
                                                        patch({
                                                            action: e.target
                                                                .value as RegionMotion['action'],
                                                            amplitude: 2,
                                                        })
                                                    }
                                                >
                                                    {Object.entries(
                                                        regionMotionLabels,
                                                    ).map(([v, l]) => (
                                                        <option
                                                            key={v}
                                                            value={v}
                                                        >
                                                            {l}
                                                        </option>
                                                    ))}
                                                </select>
                                            </label>
                                            <label>
                                                세기 (
                                                {region.action === 'rotate'
                                                    ? '도'
                                                    : '%'}
                                                )
                                                <input
                                                    aria-label="동작 세기"
                                                    className={input}
                                                    type="number"
                                                    min="0.1"
                                                    max={
                                                        region.action ===
                                                        'rotate'
                                                            ? 30
                                                            : 15
                                                    }
                                                    step="0.1"
                                                    value={region.amplitude}
                                                    onChange={(e) =>
                                                        patch({
                                                            amplitude: Number(
                                                                e.target.value,
                                                            ),
                                                        })
                                                    }
                                                />
                                            </label>
                                            <label>
                                                한 번 반복하는 시간 (초)
                                                <input
                                                    aria-label="반복 주기"
                                                    className={input}
                                                    type="number"
                                                    min="0.2"
                                                    step="0.1"
                                                    value={region.period}
                                                    onChange={(e) =>
                                                        patch({
                                                            period: Number(
                                                                e.target.value,
                                                            ),
                                                        })
                                                    }
                                                />
                                            </label>
                                            <label>
                                                반복 횟수
                                                <input
                                                    aria-label="반복 횟수"
                                                    className={input}
                                                    type="number"
                                                    min="1"
                                                    max="30"
                                                    value={region.cycles}
                                                    onChange={(e) =>
                                                        patch({
                                                            cycles: Number(
                                                                e.target.value,
                                                            ),
                                                        })
                                                    }
                                                />
                                            </label>
                                            <label>
                                                시작 자막
                                                <select
                                                    aria-label="동작 시작 자막"
                                                    className={input}
                                                    value={region.subtitleId}
                                                    onChange={(e) => {
                                                        const s =
                                                            scene?.subtitles.find(
                                                                (s) =>
                                                                    s.id ===
                                                                    e.target
                                                                        .value,
                                                            )
                                                        if (s)
                                                            patch({
                                                                subtitleId:
                                                                    s.id,
                                                                start: s.start,
                                                            })
                                                    }}
                                                >
                                                    {scene?.subtitles.map(
                                                        (s, i) => (
                                                            <option
                                                                key={s.id}
                                                                value={s.id}
                                                            >
                                                                {i + 1} ·{' '}
                                                                {s.text.slice(
                                                                    0,
                                                                    30,
                                                                )}
                                                            </option>
                                                        ),
                                                    )}
                                                </select>
                                            </label>
                                            <label>
                                                명령으로 설정
                                                <input
                                                    aria-label="동작 명령"
                                                    className={input}
                                                    placeholder="좌우로 3%씩 2초마다 3번 반복"
                                                    value={command}
                                                    onChange={(e) =>
                                                        setCommand(
                                                            e.target.value,
                                                        )
                                                    }
                                                />
                                            </label>
                                            <button
                                                className={button}
                                                onClick={() => {
                                                    try {
                                                        patch(
                                                            parseRegionMotionCommand(
                                                                command,
                                                            ),
                                                        )
                                                        setNotice(
                                                            '변환된 동작 설정을 확인한 뒤 저장해 주세요.',
                                                        )
                                                    } catch (e: any) {
                                                        setNotice(e.message)
                                                    }
                                                }}
                                            >
                                                명령을 설정에 반영
                                            </button>
                                            <button
                                                className={`${button} text-red-300`}
                                                onClick={() => {
                                                    setRegions(
                                                        regions.filter(
                                                            (_, i) =>
                                                                i !== selected,
                                                        ),
                                                    )
                                                    setSelected(0)
                                                    setDirty(true)
                                                    setVideo('')
                                                }}
                                            >
                                                이 영역 삭제
                                            </button>
                                        </>
                                    )}
                                    <p className="text-xs text-gray-400">
                                        영역은 최대 8개입니다. 정지 이미지의
                                        선택 부위를 움직이며, 기존 영상이나
                                        립싱크와 자동 합성하지 않습니다.
                                    </p>
                                </div>
                            </div>
                            <footer className="mt-4 space-y-3">
                                <p role="status" className="text-cyan-200">
                                    {notice || scene?.plan?.error || ''}
                                </p>
                                <div className="flex flex-wrap gap-2">
                                    <button
                                        disabled={busy || !sha}
                                        className={button}
                                        onClick={() => void submit('save')}
                                    >
                                        설정 저장
                                    </button>
                                    <button
                                        disabled={
                                            busy || !sha || !regions.length
                                        }
                                        className={`${button} bg-indigo-700`}
                                        onClick={() => void submit('render')}
                                    >
                                        AE 영상 만들기
                                    </button>
                                    {scene?.plan?.state === 'ready' &&
                                        !dirty && (
                                            <>
                                                <button
                                                    className={button}
                                                    onClick={async () => {
                                                        try {
                                                            const r =
                                                                await fetch(
                                                                    `${api}?preview=${scene.plan.id}`,
                                                                    { headers },
                                                                )
                                                            const data =
                                                                await r.json()
                                                            if (!r.ok)
                                                                throw new Error(
                                                                    data.error,
                                                                )
                                                            setVideo(data.url)
                                                        } catch (e: any) {
                                                            setNotice(e.message)
                                                        }
                                                    }}
                                                >
                                                    AE 결과 보기
                                                </button>
                                                <button
                                                    className={`${button} bg-emerald-700`}
                                                    disabled={busy || !video}
                                                    onClick={() =>
                                                        void submit('apply')
                                                    }
                                                >
                                                    확인한 영상을 씬에 적용
                                                </button>
                                            </>
                                        )}
                                </div>
                            </footer>
                        </section>
                    </div>,
                    document.body,
                )}
        </>
    )
}
