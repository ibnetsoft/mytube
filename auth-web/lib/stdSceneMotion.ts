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

/** Use scene time (not subtitle time), so wrapping a sentence never restarts motion. */
export function sceneMotionStyle(effect: string, time: number, start: number, end: number) {
    const progress = Math.max(0, Math.min(1, (time - start) / Math.max(0.001, end - start)))
    let scale = 1
    let x = 0
    let y = 0
    if (effect === 'zoom_in') scale = 1 + 0.15 * progress
    if (effect === 'zoom_out') scale = 1.15 - 0.15 * progress
    if (effect.startsWith('pan_')) {
        scale = 1.2
        const offset = 10 - 20 * progress
        if (effect === 'pan_left') x = offset
        if (effect === 'pan_right') x = -offset
        if (effect === 'pan_up') y = offset
        if (effect === 'pan_down') y = -offset
    }
    return { transform: `translate(${x}%, ${y}%) scale(${scale})`, transformOrigin: 'center', willChange: 'transform' }
}
