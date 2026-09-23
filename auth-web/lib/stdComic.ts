import layouts from '../public/comic/layouts.json'

export type ComicMode = 'standard' | 'comic' | 'moving_comic'
export type ComicLayout = keyof typeof layouts
export type ComicLettering = {kind?: 'narration' | 'dialogue'; style?: 'speech' | 'shout' | 'whisper'; x?: number; y?: number; width?: number; target_x?: number; target_y?: number}
export type ComicSettings = {
    version: 1; mode: ComicMode; layout: ComicLayout; turn_duration: number
    turn_sound: boolean; dim_inactive: boolean; font_size: number
    page_layouts: Record<string, ComicLayout>
    lettering: Record<string, ComicLettering>
    panels: Record<string, { fit?: 'contain' | 'cover'; bubble_position?: 'top' | 'bottom'; motion?: 'still' | 'pan' | 'video' }>
}
export const COMIC_LAYOUTS = layouts
export const COMIC_LAYOUT_LABELS: Record<ComicLayout, string> = {
    spread: '좌우 2컷', single: '전체 1컷', grid: '4컷', inset: '큰 컷 + 인셋',
    grid6:'정규 격자 2×3', asymmetric:'비대칭 · 큰 컷과 반응 2컷', wide:'가로 와이드 2컷', long:'세로 롱 3컷',
    diagonal:'대각선 분할', splash:'스플래시', double:'양면 펼침', borderless:'테두리 없는 2컷',
    bleed:'블리드', sequence:'연속 동작 4컷', parallel:'대응·평행 2컷', breakout:'경계 돌파 · 투명 전경 필요',
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
        panels[key] = { fit: p.fit === 'cover' ? 'cover' : 'contain', bubble_position: p.bubble_position === 'top' ? 'top' : 'bottom', motion: ['still','pan','video'].includes(p.motion) ? p.motion : undefined }
    }
    const page_layouts: ComicSettings['page_layouts'] = {}, lettering: ComicSettings['lettering'] = {}
    for (const [k,v] of Object.entries(raw.page_layouts || {}).slice(0,1000)) if (/^\d+$/.test(k) && typeof v==='string' && Object.hasOwn(layouts,v)) page_layouts[k]=v as ComicLayout
    for (const [k,v] of Object.entries(raw.lettering || {}).slice(0,10000)) {
        if (!/^\d+:\d+$/.test(k) || !v || typeof v!=='object') continue
        const b=v as ComicLettering, clean: ComicLettering={}
        if (b.kind==='dialogue' || b.kind==='narration') clean.kind=b.kind
        if (['speech','shout','whisper'].includes(b.style || '')) clean.style=b.style
        for (const field of ['x','y','width','target_x','target_y'] as const) if (b[field]!=null) clean[field]=finite(b[field],field==='width'?.9:.05,field==='width'?.2:0,field==='width'?.94:1)
        lettering[k]=clean
    }
    return { version: 1, mode, layout: Object.hasOwn(layouts, raw.layout) ? raw.layout : 'spread',
        turn_duration: finite(raw.turn_duration ?? 0.7, 0.7, 0.3, 1.5),
        turn_sound: raw.turn_sound !== false, dim_inactive: raw.dim_inactive === true,
        font_size: finite(raw.font_size ?? 28, 28, 18, 44), panels, page_layouts, lettering }
}
export function comicSettingsForProject(project: any): ComicSettings {
    return normalizeComicSettings(project?.project_payload?.render_settings?.comic ?? project?.project_payload?.structure?.comic_plan?.render_settings)
}
export function isComicProject(project: any): boolean {
    const value = project?.project_payload?.render_settings?.comic ?? project?.project_payload?.structure?.comic_plan?.render_settings
    return value?.version === 1 && (value.mode === 'comic' || value.mode === 'moving_comic')
}
export function selectComicMedia<T>(mode: ComicMode, image: T | undefined, video: T | undefined): T | undefined {
    return mode === 'comic' ? image || video : video || image
}
export function comicPages<T>(scenes: T[], settings: ComicSettings): T[][] {
    const pages: T[][]=[]
    for (let cursor=0;cursor<scenes.length;) {
        const size=layouts[settings.page_layouts?.[String(pages.length)] || settings.layout].length
        pages.push(scenes.slice(cursor,cursor+size));cursor+=size
    }
    return pages
}
export function comicSettingsWithUploadedVideo(project: any, sceneNumber: number): ComicSettings {
    const settings = comicSettingsForProject(project)
    if (settings.mode !== 'moving_comic') return settings
    const key = String(sceneNumber)
    return {...settings, panels: {...settings.panels, [key]: {...settings.panels[key], motion: 'video'}}}
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
