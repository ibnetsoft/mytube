import layouts from '../public/comic/layouts.json'

export type ComicMode = 'standard' | 'comic' | 'moving_comic'
export type ComicLayout = keyof typeof layouts
export type ComicSettings = {
    version: 1; mode: ComicMode; layout: ComicLayout; turn_duration: number
    turn_sound: boolean; dim_inactive: boolean; font_size: number
    panels: Record<string, { fit?: 'contain' | 'cover'; bubble_position?: 'top' | 'bottom' }>
}
export const COMIC_LAYOUTS = layouts
export const COMIC_LAYOUT_LABELS: Record<ComicLayout, string> = {
    spread: '좌우 2컷', single: '전체 1컷', grid: '4컷', inset: '큰 컷 + 인셋',
}
const finite = (v: unknown, fallback: number, low: number, high: number) =>
    Number.isFinite(Number(v)) ? Math.min(high, Math.max(low, Number(v))) : fallback

export function normalizeComicSettings(value: any): ComicSettings {
    const raw = value && typeof value === 'object' ? value : {}
    const mode = raw.version === 1 && ['comic', 'moving_comic'].includes(raw.mode) ? raw.mode : 'standard'
    const panels: ComicSettings['panels'] = {}
    for (const [key, val] of Object.entries(raw.panels || {}).slice(0, 1000)) {
        if (!/^\d+$/.test(key) || !val || typeof val !== 'object') continue
        const p = val as any
        panels[key] = { fit: p.fit === 'cover' ? 'cover' : 'contain', bubble_position: p.bubble_position === 'top' ? 'top' : 'bottom' }
    }
    return { version: 1, mode, layout: Object.hasOwn(layouts, raw.layout) ? raw.layout : 'spread',
        turn_duration: finite(raw.turn_duration ?? 0.7, 0.7, 0.3, 1.5),
        turn_sound: raw.turn_sound !== false, dim_inactive: raw.dim_inactive === true,
        font_size: finite(raw.font_size ?? 28, 28, 18, 44), panels }
}
export function comicSettingsForProject(project: any): ComicSettings {
    return normalizeComicSettings(project?.project_payload?.render_settings?.comic)
}
export function isComicProject(project: any): boolean {
    const value = project?.project_payload?.render_settings?.comic
    return value?.version === 1 && (value.mode === 'comic' || value.mode === 'moving_comic')
}
export function selectComicMedia<T>(mode: ComicMode, image: T | undefined, video: T | undefined): T | undefined {
    return mode === 'comic' ? image || video : video || image
}
export function comicPages<T>(scenes: T[], settings: ComicSettings): T[][] {
    const size = layouts[settings.layout].length
    return Array.from({ length: Math.ceil(scenes.length / size) }, (_, i) => scenes.slice(i * size, (i + 1) * size))
}
// Preview uses the same scene-local clock as the worker. Missing TTS uses scene duration.
export function comicSceneTimings(scenes: any[], subtitles: any[], audioDuration = 0) {
    let cursor = 0
    const items = scenes.map((scene, i) => {
        const sceneNumber = Number(scene.scene_number || i + 1)
        const blocks = subtitles.filter(s => Number(s.scene_number) === sceneNumber)
        const starts = blocks.map(s => Number(s.start_time ?? s.start)).filter(Number.isFinite)
        const ends = blocks.map(s => Number(s.end_time ?? s.end)).filter(Number.isFinite)
        const candidate = starts.length ? Math.min(...starts) : cursor
        const start = i === 0 ? 0 : Math.max(cursor, candidate)
        const end = Math.max(start + 0.1, ends.length ? Math.max(...ends) : start + Number(scene.duration_seconds || scene.target_duration || 5))
        cursor = end
        return { start, end, duration: end - start, sceneNumber, blocks }
    })
    return items.map((item, i) => {
        const end = i + 1 < items.length ? items[i + 1].start : Math.max(item.start + 2, audioDuration || item.end)
        return { ...item, end, duration: end - item.start }
    })
}
