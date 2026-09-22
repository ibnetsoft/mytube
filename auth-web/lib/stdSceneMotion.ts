export const SCENE_MOTIONS = [
    { id: 'zoom_in', label: 'Zoom In · 확대' },
    { id: 'zoom_out', label: 'Zoom Out · 축소' },
    { id: 'pan_left', label: 'Pan Left · 왼쪽 이동' },
    { id: 'pan_right', label: 'Pan Right · 오른쪽 이동' },
    { id: 'pan_up', label: 'Pan Up · 위로 이동' },
    { id: 'pan_down', label: 'Pan Down · 아래로 이동' },
    { id: 'none', label: '없음 · 정지' },
] as const

export function sceneMotion(scene: any): string {
    const value = scene?.metadata?.image_effect || scene?.image_effect
    return SCENE_MOTIONS.some(item => item.id === value) ? value : 'zoom_in'
}

export function sceneMotionSpeed(scene: any): number {
    const raw = scene?.metadata?.motion_speed ?? scene?.motion_speed
    const value = Number(raw)
    return raw != null && raw !== '' && Number.isFinite(value) && value > 0
        ? Math.max(0.5, Math.min(3, value)) : sceneMotion(scene).startsWith('zoom_') ? 1.5 : 1
}

/** Use scene time (not subtitle time), so wrapping a sentence never restarts motion. */
export function sceneMotionStyle(effect: string, time: number, start: number, end: number, speed = effect.startsWith('zoom_') ? 1.5 : 1) {
    const progress = Math.max(0, Math.min(1, (time - start) / Math.max(0.001, end - start)))
    const eased = (1 - Math.cos(Math.PI * progress)) / 2
    speed = Number.isFinite(speed) ? Math.max(0.5, Math.min(3, speed)) : 1
    let scale = 1
    let x = 0
    let y = 0
    if (effect === 'zoom_in') scale = 1 + 0.04 * speed * eased
    if (effect === 'zoom_out') scale = 1 + 0.04 * speed * (1 - eased)
    if (effect.startsWith('pan_')) {
        scale = 1 + 0.12 * speed
        const offset = 6 * speed * (1 - 2 * eased)
        if (effect === 'pan_left') x = offset
        if (effect === 'pan_right') x = -offset
        if (effect === 'pan_up') y = offset
        if (effect === 'pan_down') y = -offset
    }
    return { transform: `translate(${x}%, ${y}%) scale(${scale})`, transformOrigin: 'center', willChange: 'transform' }
}
