export type MotionPoint = [number, number]
export type RegionMotion = {
    id: string
    name: string
    polygon: MotionPoint[]
    anchor: MotionPoint
    action: 'horizontal' | 'vertical' | 'rotate' | 'scale' | 'bend' | 'walk' | 'hold'
    amplitude: number
    period: number
    cycles: number
    subtitleId: string
    start: number
    direction?: 1 | -1
    parentId?: string
    restAngle?: number
    phaseOffset?: number
    walkPart?: 'upper' | 'lower'
    contour?: 'auto' | 'exact'
    occluded?: boolean
    replacementAssetId?: string
}
export const regionMotionLabels = {
    hold: '자세 유지',
    bend: '관절 굽히기',
    walk: '걷기 · 제자리 보행',
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
export function motionSceneTimeline(subtitles: any[], number: number, nonverbalScene?: any): { duration: number; subtitles: { id: string; text: string; start: number; end: number }[] } {
    if (nonverbalScene?.joint_motion_plan?.contract === 'ae_joint_rig/v1' && nonverbalScene?.scene_timeline) {
        const t = nonverbalScene.scene_timeline
        if (!finite(t.duration, .1, 300) || !Array.isArray(t.cues)) throw new Error('행동 타임라인을 확인해 주세요.')
        return { duration: t.duration as number, subtitles: t.cues.map((c: any) => {
            if (typeof c.id !== 'string' || !finite(c.start,0,t.duration) || !finite(c.end,c.start,t.duration)) throw new Error('행동 시작점이 올바르지 않습니다.')
            return {id:c.id, text:String(c.text || '행동 시작'), start:c.start as number, end:c.end as number}
        }) }
    }
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
    if (!Array.isArray(input) || !input.length || input.length > 32)
        throw new Error('움직일 영역을 1~32개 지정해 주세요.')
    if (!finite(timeline.duration, 0.1, 300))
        throw new Error(
            '씬 자막의 재생 시간을 먼저 저장해 주세요. 최대 5분 씬을 지원합니다.',
        )
    const ids = new Set<string>()
    const rows: RegionMotion[] = input.map((r: any): RegionMotion => {
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
            !finite(r.amplitude, 0.1, ['rotate', 'bend', 'walk'].includes(r.action) ? 120 : 15) ||
            !finite(r.period, 0.2, 30) ||
            !Number.isInteger(r.cycles) ||
            r.cycles < 1 ||
            r.cycles > 30
        )
            throw new Error('동작의 세기·주기·반복 횟수를 확인해 주세요.')
        if (!finite(r.restAngle ?? 0, -180, 180) || !finite(r.phaseOffset ?? 0, 0, 1)
            || !['upper', 'lower'].includes(r.walkPart ?? 'upper') || ![1, -1].includes(r.direction ?? 1))
            throw new Error('관절 각도·보행 위상을 확인해 주세요.')
        if (r.parentId !== undefined && typeof r.parentId !== 'string')
            throw new Error('부모 관절 ID가 올바르지 않습니다.')
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
            ...(r.direction !== undefined ? { direction: r.direction } : {}),
            ...(r.parentId ? { parentId: r.parentId } : {}),
            ...(r.restAngle !== undefined ? { restAngle: r.restAngle } : {}),
            ...(r.phaseOffset !== undefined ? { phaseOffset: r.phaseOffset } : {}),
            ...(r.walkPart !== undefined ? { walkPart: r.walkPart } : {}),
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
    for (const row of rows) {
        const seen = new Set([row.id])
        let parent = row.parentId
        while (parent) {
            if (seen.has(parent)) throw new Error('관절 연결에 순환이 있습니다.')
            seen.add(parent)
            const node = rows.find((r) => r.id === parent)
            if (!node) throw new Error('부모 관절이 없습니다.')
            parent = node.parentId
        }
        if ((row.action === 'bend' || row.action === 'walk') && !row.parentId)
            throw new Error('관절 굽히기·걷기는 먼저 부모 부위를 연결해 주세요.')
    }
    return rows
}
// Restricted command grammar; unsupported prose never becomes executable AE code.
export function parseRegionMotionCommand(
    command: string,
): Partial<RegionMotion> {
    if (/뛰|손가락|run|finger|วิ่ง|นิ้ว/i.test(command))
        throw new Error(
            '달리기·손가락 동작은 개별 관절을 직접 설정해 주세요.',
        )
    const actions: RegionMotion['action'][] = []
    if (/걷|walk|เดิน/i.test(command)) actions.push('walk')
    if (/관절|굽히|구부|bend|งอ/i.test(command)) actions.push('bend')
    if (/좌우|왼쪽|오른쪽|horizontal|left|right|ซ้าย|ขวา/i.test(command))
        actions.push('horizontal')
    if (/상하|위아래|vertical|up and down|ขึ้น|ลง/i.test(command))
        actions.push('vertical')
    if (/회전|흔들|기울|rotate|swing|tilt|wave|หมุน|แกว่ง|เอียง/i.test(command))
        actions.push('rotate')
    if (/확대|축소|크기|scale|zoom|숨쉬|ขยาย|ย่อ/i.test(command)) actions.push('scale')
    // "좌우로 흔들기" is a translation unless rotation was explicitly requested.
    const action = actions.includes('walk') ? 'walk' : actions.includes('bend') ? 'bend' :
        actions.includes('horizontal') && !/회전|rotate|หมุน/i.test(command)
            ? 'horizontal'
            : actions.at(-1)
    if (!action)
        throw new Error(
            '예: “좌우로 3%씩 2초마다 3번 반복”, “15도 회전, 1초마다 4번”',
        )
    const amplitude = command.match(/(\d+(?:\.\d+)?)\s*(?:%|도|degrees?|องศา)/i)
    const period = command.match(/(\d+(?:\.\d+)?)\s*(?:초|seconds?|sec|วินาที)/i)
    const cycles = command.match(/(\d+)\s*(?:번|회|times?|ครั้ง)/i)
    return {
        action,
        amplitude: amplitude
            ? Number(amplitude[1])
            : ['rotate', 'bend', 'walk'].includes(action)
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
            direction: undefined,
            parentId: undefined,
            restAngle: undefined,
            phaseOffset: undefined,
            walkPart: undefined,
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

// Full-canvas transforms: child motion is expressed relative to its rest anchor.
export function motionAngle(region: RegionMotion, time: number) {
    const elapsed = time - region.start
    const active = elapsed > 0 && elapsed < region.period * region.cycles
    const theta = 2 * Math.PI * (elapsed / region.period + (region.phaseOffset || 0))
    const wave = !active ? 0 : region.action === 'walk' && region.walkPart === 'lower'
        ? Math.max(0, Math.sin(theta)) : Math.sin(theta)
    return (region.restAngle || 0) + region.amplitude * wave * (region.direction || 1)
}
type Matrix = [number, number, number, number, number, number]
function multiply(a: Matrix, b: Matrix): Matrix {
    return [a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
        a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
        a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5]]
}
export function regionTransform(regions: RegionMotion[], id: string, time: number, size: [number, number]): Matrix {
    const seen = new Set<string>()
    function visit(key: string): Matrix {
        const r = regions.find((item) => item.id === key)
        if (!r || seen.has(key)) return [1,0,0,1,0,0]
        seen.add(key)
        const x = r.anchor[0]*size[0], y = r.anchor[1]*size[1]
        const v = motionPhase(r, time)*r.amplitude
        const angle = (['rotate','bend','walk'].includes(r.action) ? motionAngle(r,time) : (r.restAngle || 0))*Math.PI/180
        const scale = r.action === 'scale' ? 1+v/100 : 1
        const c = Math.cos(angle)*scale, s = Math.sin(angle)*scale
        const own: Matrix = [c,s,-s,c,x-c*x+s*y+(r.action==='horizontal'?v*size[0]/100:0),y-s*x-c*y+(r.action==='vertical'?v*size[1]/100:0)]
        return r.parentId ? multiply(visit(r.parentId), own) : own
    }
    return visit(id)
}
