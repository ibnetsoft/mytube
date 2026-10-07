export type MotionPoint = [number, number]
export type RegionMotion = {
    id: string
    name: string
    polygon: MotionPoint[]
    anchor: MotionPoint
    action: 'horizontal' | 'vertical' | 'rotate' | 'scale'
    amplitude: number
    period: number
    cycles: number
    subtitleId: string
    start: number
    contour?: 'auto' | 'exact'
    occluded?: boolean
    replacementAssetId?: string
}
export const regionMotionLabels = {
    horizontal: '좌우 반복',
    vertical: '상하 반복',
    rotate: '흔들기·회전',
    scale: '확대·축소 반복',
}
const finite = (value: unknown, min: number, max: number) =>
    typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= min &&
    value <= max
const point = (p: any): p is MotionPoint =>
    Array.isArray(p) && p.length === 2 && p.every((n) => finite(n, 0, 1))
export function motionSceneTimeline(subtitles: any[], number: number) {
    const rows = subtitles
        .map((r, i) => ({
            id: String(r.id || `index-${i}`),
            text: String(r.text || ''),
            scene: Number(r.scene_number),
            start: Number(r.start_num ?? r.start_time ?? r.start),
            end: Number(r.end_num ?? r.end_time ?? r.end),
        }))
        .filter(
            (r) =>
                r.scene === number &&
                Number.isFinite(r.start) &&
                Number.isFinite(r.end) &&
                r.end > r.start,
        )
    const start = rows.length ? Math.min(...rows.map((r) => r.start)) : 0
    const duration = rows.length
        ? Math.max(...rows.map((r) => r.end)) - start
        : 0
    return {
        duration,
        subtitles: rows.map((r) => ({
            id: r.id,
            text: r.text,
            start: r.start - start,
            end: r.end - start,
        })),
    }
}
export function validateRegionMotions(
    input: unknown,
    timeline: ReturnType<typeof motionSceneTimeline>,
): RegionMotion[] {
    if (!Array.isArray(input) || !input.length || input.length > 8)
        throw new Error('움직일 영역을 1~8개 지정해 주세요.')
    if (!finite(timeline.duration, 0.1, 300))
        throw new Error(
            '씬 자막의 재생 시간을 먼저 저장해 주세요. 최대 5분 씬을 지원합니다.',
        )
    const ids = new Set<string>()
    return input.map((r: any) => {
        if (
            typeof r.id !== 'string' ||
            !/^[a-zA-Z0-9_-]{1,64}$/.test(r.id) ||
            ids.has(r.id)
        )
            throw new Error('영역 ID가 올바르지 않습니다.')
        ids.add(r.id)
        if (
            !Array.isArray(r.polygon) ||
            r.polygon.length < 3 ||
            r.polygon.length > 32 ||
            !r.polygon.every(point) ||
            !point(r.anchor)
        )
            throw new Error('영역 외곽선과 고정점을 지정해 주세요.')
        const area =
            Math.abs(
                r.polygon.reduce((sum: number, p: MotionPoint, i: number) => {
                    const next = r.polygon[(i + 1) % r.polygon.length]
                    return sum + p[0] * next[1] - next[0] * p[1]
                }, 0),
            ) / 2
        if (area < 0.0001 || area > 0.7)
            throw new Error('영역은 이미지의 70% 이하로 지정해 주세요.')
        if (
            !Object.hasOwn(regionMotionLabels, r.action) ||
            !finite(r.amplitude, 0.1, r.action === 'rotate' ? 30 : 15) ||
            !finite(r.period, 0.2, 30) ||
            !Number.isInteger(r.cycles) ||
            r.cycles < 1 ||
            r.cycles > 30
        )
            throw new Error('동작의 세기·주기·반복 횟수를 확인해 주세요.')
        const subtitle = timeline.subtitles.find((s) => s.id === r.subtitleId)
        if (
            !subtitle ||
            subtitle.start + r.period * r.cycles > timeline.duration + 0.001
        )
            throw new Error(
                '시작 자막부터 씬 끝까지 동작이 들어가도록 주기나 반복 횟수를 줄여 주세요.',
            )
        return {
            id: r.id,
            name: String(r.name || '영역').slice(0, 60),
            polygon: r.polygon.map((p: MotionPoint) => [...p]),
            anchor: [r.anchor[0], r.anchor[1]] as MotionPoint,
            action: r.action,
            amplitude: r.amplitude,
            period: r.period,
            cycles: r.cycles,
            subtitleId: subtitle.id,
            start: subtitle.start,
            contour: r.contour === 'exact' ? 'exact' : 'auto',
            occluded: r.occluded === true,
            replacementAssetId: String(r.replacementAssetId || ''),
        }
    })
}
// Restricted command grammar; unsupported prose never becomes executable AE code.
export function parseRegionMotionCommand(
    command: string,
): Partial<RegionMotion> {
    if (/걷|뛰|손가락|관절|굽히|구부|walk|run|finger|bend/i.test(command))
        throw new Error(
            '관절을 구부리는 동작은 지원하지 않습니다. 좌우·상하 이동, 회전, 확대·축소 중 선택해 주세요.',
        )
    const actions: RegionMotion['action'][] = []
    if (/좌우|왼쪽|오른쪽|horizontal|left|right/i.test(command))
        actions.push('horizontal')
    if (/상하|위아래|vertical|up and down/i.test(command))
        actions.push('vertical')
    if (/회전|흔들|기울|rotate|swing|tilt|wave/i.test(command))
        actions.push('rotate')
    if (/확대|축소|크기|scale|zoom|숨쉬/i.test(command)) actions.push('scale')
    // "좌우로 흔들기" is a translation unless rotation was explicitly requested.
    const action =
        actions.includes('horizontal') && !/회전|rotate/i.test(command)
            ? 'horizontal'
            : actions.at(-1)
    if (!action)
        throw new Error(
            '예: “좌우로 3%씩 2초마다 3번 반복”, “15도 회전, 1초마다 4번”',
        )
    const amplitude = command.match(/(\d+(?:\.\d+)?)\s*(?:%|도|degrees?)/i)
    const period = command.match(/(\d+(?:\.\d+)?)\s*(?:초|seconds?|sec)/i)
    const cycles = command.match(/(\d+)\s*(?:번|회|times?)/i)
    return {
        action,
        amplitude: amplitude
            ? Number(amplitude[1])
            : action === 'rotate'
              ? 8
              : 2,
        ...(period ? { period: Number(period[1]) } : {}),
        ...(cycles ? { cycles: Number(cycles[1]) } : {}),
    }
}
export function motionPhase(region: RegionMotion, time: number) {
    const elapsed = time - region.start
    return elapsed <= 0 || elapsed >= region.period * region.cycles
        ? 0
        : Math.sin((2 * Math.PI * elapsed) / region.period)
}

// Layer identity deliberately excludes animation settings and subtitle timing.
export function regionLayerGeometry(regions: any[]) {
    return validateRegionMotions(
        regions.map((r) => ({
            ...r,
            action: 'horizontal',
            amplitude: 1,
            period: 1,
            cycles: 1,
            subtitleId: 'layer',
        })),
        {
            duration: 1,
            subtitles: [{ id: 'layer', text: '', start: 0, end: 1 }],
        },
    ).map((r, i) => ({
        id: r.id,
        polygon: r.polygon,
        contour: regions[i].contour === 'exact' ? 'exact' : 'auto',
        occluded: regions[i].occluded === true,
        replacementAssetId: String(regions[i].replacementAssetId || ''),
    }))
}
export function regionLayerKey(
    imageId: string,
    imageSha256: string,
    regions: any[],
    backgroundAssetId = '',
) {
    return JSON.stringify({
        version: 1,
        imageId,
        imageSha256,
        geometry: regionLayerGeometry(regions),
        backgroundAssetId,
    })
}
