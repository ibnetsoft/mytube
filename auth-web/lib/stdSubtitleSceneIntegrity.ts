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
