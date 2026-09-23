import { getTranslation, type SupportedLocale } from './i18n'
import { COMIC_LAYOUTS, comicSettingsForProject } from './stdComic'

// Generation tools accept rectangular clips. Choose a common ratio near the
// panel's physical dimensions on the 16:9 page, not its normalized coordinates.
const RATIOS = [
    { label: '9:16', width: 9, height: 16 },
    { label: '3:4', width: 3, height: 4 },
    { label: '1:1', width: 1, height: 1 },
    { label: '4:3', width: 4, height: 3 },
    { label: '16:9', width: 16, height: 9 },
]
export function sceneVideoGeneration(project: any, sceneIndex: number) {
    const settings = comicSettingsForProject(project)
    if (settings.mode === 'standard') return { ...RATIOS[4], comic: false }
    let remaining = Number.isFinite(sceneIndex) ? Math.max(0, Math.floor(sceneIndex)) : 0
    let pageIndex = 0
    let panels = COMIC_LAYOUTS[settings.page_layouts[String(pageIndex)] || settings.layout]
    while (remaining >= panels.length) {
        remaining -= panels.length
        pageIndex += 1
        panels = COMIC_LAYOUTS[settings.page_layouts[String(pageIndex)] || settings.layout]
    }
    const panel = panels[remaining]
    const target = (panel[2] * 16) / (panel[3] * 9)
    const ratio = RATIOS.reduce((best, next) =>
        Math.abs(Math.log((next.width / next.height) / target)) < Math.abs(Math.log((best.width / best.height) / target)) ? next : best)
    return { ...ratio, comic: true }
}

export function videoPromptWithRatio(prompt: string, spec: ReturnType<typeof sceneVideoGeneration>) {
    // Remove previous generated headers and conventional ratio directives so a
    // saved prompt cannot instruct the user to generate two different ratios.
    const body = prompt.replace(/^\[Video generation settings\][\s\S]*?\[Scene prompt\]\s*/i, '')
        .replace(/--ar\s+\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?/gi, '')
        .replace(/\b(?:aspect\s+ratio\s*[:=]?\s*)?(?:16:9|9:16|3:4|4:3|1:1|21:9)\b(?:\s*aspect\s+ratio)?/gi, match => match.replace(/\d+(?:\.\d+)?\s*:\s*\d+(?:\.\d+)?/, spec.label))
        .trim()
    return `[Video generation settings]\nAspect ratio: ${spec.label} (width:height). Set the video tool's aspect-ratio selector to ${spec.label}; prompt text alone may not set the output size.${spec.comic ? '\nGenerate one rectangular scene clip only. Keep faces and important action away from the edges. Do not add comic panel borders, speech bubbles, text, or page-turn effects; the platform adds these during composition.' : ''}\n\n[Scene prompt]\n${body}`
}

export function videoRatioLabels(locale: SupportedLocale) {
    return {
        title: getTranslation(locale, 'video_ratio_title'),
        note: getTranslation(locale, 'video_ratio_note'),
        page: getTranslation(locale, 'video_ratio_page'),
    }
}
