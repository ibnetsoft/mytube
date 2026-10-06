// Never substitute an array position, the first image, or a cached subtitle
// image for a missing storyboard scene. Missing data must remain visible.
export function findExactSubtitleScene(subtitle: any, scenes: any[], payloadScenes: any[] = []): any | null {
    const number = Number(subtitle?.scene_number ?? subtitle?.scene ?? subtitle?.sceneNumber)
    if (!Number.isInteger(number) || number < 1) return null
    const matches = (scene: any) => Number(scene?.scene_number ?? scene?.scene_order) === number
    const authoritativeScenes = scenes.length ? scenes : payloadScenes
    return authoritativeScenes.find(matches) || null
}

export function subtitlesMatchSceneManifest(subtitles: any[], scenes: any[]): boolean {
    if (!Array.isArray(subtitles) || !subtitles.length || !Array.isArray(scenes) || !scenes.length) return false
    const expected = new Set(scenes.map(scene => Number(scene?.scene_number ?? scene?.scene_order)))
    if (expected.size !== scenes.length || [...expected].some(n => !Number.isInteger(n) || n < 1)) return false
    const actual = new Set<number>()
    let previous = 0
    for (const subtitle of subtitles) {
        const number = Number(subtitle?.scene_number)
        if (!expected.has(number) || number < previous) return false
        previous = number
        actual.add(number)
    }
    return actual.size === expected.size
}

/** A scene disappears only through an explicit editor deletion, never a partial snapshot. */
export function preserveSubtitleScenes(incoming: any[], previous: any[], scenes: any[], deleted: number[] = []) {
    const excluded = new Set(deleted.map(Number))
    const numberOf = (row: any) => Number(row.scene_number ?? row.scene_order)
    const rows = incoming.filter(row => !excluded.has(numberOf(row))).map(row => ({ ...row }))
    const present = new Set(rows.map(numberOf))
    const recovered: number[] = []
    const manifest = new Map<number, any>()
    for (const scene of scenes) manifest.set(numberOf(scene), scene)
    for (const row of previous) if (!manifest.has(numberOf(row))) manifest.set(numberOf(row), {})
    for (const [number, scene] of manifest) {
        if (!Number.isFinite(number) || number <= 0 || excluded.has(number) || present.has(number)) continue
        const saved = previous.filter(row => numberOf(row) === number)
        if (saved.length) rows.push(...saved.map(row => ({ ...row })))
        else {
            const text = String(scene.scene_text || scene.narration || scene.script_excerpt || '').trim()
            if (!text) continue
            // Source text is recoverable; its draft timing and speaker are not a verified recording.
            rows.push({ id: `sub-${number}-source-recovery`, scene_number: number, text,
                start_num: 0, end_num: 0, start_time: '0.0', end_time: '0.0',
                restored_audio_pending: true, audio_regeneration_required: true,
                voice_assignment_pending: true })
        }
        present.add(number)
        recovered.push(number)
    }
    // Stable sorting retains manual splits and the order of existing rows within each scene.
    rows.sort((a, b) => numberOf(a) - numberOf(b))
    return { subtitles: rows, recovered }
}
