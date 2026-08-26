export interface StdSubtitleItem {
    id: string
    scene_number: number
    start_time: string
    end_time: string
    start_num: number
    end_num: number
    text: string
    image_url?: string
    video_url?: string | null
    is_hook_zone: boolean
}

export interface SceneTiming {
    scene_number: number
    start_time: number
    end_time: number
    duration: number
    is_video_required: boolean
}

export const BASE_STORY_SCENE_COUNT = 53
export const SENIOR_READING_CHARS_PER_SECOND = 5.0
export const DEFAULT_SENIOR_SUBTITLE_MAX_CHARS = 20

function readingBudgetForDuration(durationSeconds: number): number {
    return Math.max(5, Math.floor(durationSeconds * SENIOR_READING_CHARS_PER_SECOND))
}

function findNaturalCut(text: string, start: number, hardLimit: number): number {
    if (hardLimit >= text.length) return text.length

    const softStart = Math.max(start + 1, hardLimit - 12)
    const softEnd = Math.min(text.length, hardLimit + 6)
    const slice = text.slice(softStart, softEnd)
    const punctuationMatch = slice.match(/[.!?。！？…]/)
    if (punctuationMatch?.index !== undefined) {
        return softStart + punctuationMatch.index + 1
    }

    const before = text.lastIndexOf(' ', hardLimit)
    if (before > start && before >= hardLimit - 10) return before + 1

    const after = text.indexOf(' ', hardLimit)
    if (after !== -1 && after <= hardLimit + 6) return after + 1

    return hardLimit
}

export function sceneNarrationText(scene: any): string {
    return String(
        scene?.scene_text
        || scene?.script_excerpt
        || scene?.script_text
        || scene?.narration_text
        || scene?.narration
        || scene?.text
        || scene?.prompt_ko
        || ''
    ).trim()
}

function normalizedScriptText(rawScriptText: string): string {
    return stripGeneratedPlanningText(rawScriptText)
        .split('\n')
        .map(l => l.trim())
        .filter(l => l.length > 0)
        .map(l => l.replace(/^(?:speaker\s*\d+|host|narrator)\s*[:：-]\s*/i, '').trim())
        .filter(l => l.length > 0)
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim()
}

export function stripGeneratedPlanningText(rawScriptText: string | null | undefined): string {
    const text = String(rawScriptText || '').trim()
    if (!text) return ''

    return text
        .split(/\n\s*\n+/)
        .map(part => part.trim())
        .filter(part => {
            if (!part) return false
            return !(
                /\d+\s*\uBC88\uC9F8\s*\uC7A5\uBA74/.test(part)
                || /Opening beat/i.test(part)
                || /Create immediate/i.test(part)
                || /Leave one story secret/i.test(part)
                || /unresolved into the next beat/i.test(part)
                || /Reference technique from benchmark/i.test(part)
                || /Timed\s+\w+\s+visual beat/i.test(part)
            )
        })
        .join('\n\n')
        .trim()
}

export function cleanKoreanScriptLine(text: string): string {
    if (!text) return ''
    const cleaned = stripGeneratedPlanningText(text)
        .replace(/First-minute micro beat.*?:/gi, '')
        .replace(/Opening beat.*?(?:\.|$)/gi, '')
        .replace(/Create immediate.*?(?:\.|$)/gi, '')
        .replace(/Leave one story secret.*?(?:\.|$)/gi, '')
        .replace(/Keep this as a separate.*?hook:/gi, '')
        .replace(/The shot uses.*?photorealism\./gi, '')
        .replace(/Cinematic.*?8k/gi, '')
        .replace(/At the funeral hall.*?:/gi, '')
        .replace(/Scene \d+.*?:/gi, '')
        .replace(/\[Scene \d+\]/gi, '')
        .replace(/[\r\n]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()

    if (/^[A-Za-z0-9\s,\.?!'"\-:;]+$/.test(cleaned) && !/[\uAC00-\uD7A3]/.test(cleaned)) {
        return ''
    }

    const match = cleaned.match(/[\uAC00-\uD7A30-9\s,\.?!'"~]+/g)
    if (match) return match.join('').replace(/\s+/g, ' ').trim()
    return cleaned
}

export function getStandardSceneDuration(sceneNumber: number): number {
    if (sceneNumber <= 12) return 5.0
    if (sceneNumber <= 28) return 15.0
    if (sceneNumber <= 43) return 20.0
    if (sceneNumber <= BASE_STORY_SCENE_COUNT) return 30.0
    return 60.0
}

export function estimateRequiredSceneCount(rawScriptText: string, existingSceneCount: number = BASE_STORY_SCENE_COUNT): number {
    const textLength = normalizedScriptText(rawScriptText).length
    const minimumScenes = Math.max(BASE_STORY_SCENE_COUNT, existingSceneCount || BASE_STORY_SCENE_COUNT)
    if (textLength <= 0) return minimumScenes

    let sceneCount = 0
    let budget = 0
    while (sceneCount < minimumScenes || budget < textLength) {
        sceneCount += 1
        budget += readingBudgetForDuration(getStandardSceneDuration(sceneCount))
    }

    return sceneCount
}

export function calculateLongformSceneTimings(scenes: any[]): SceneTiming[] {
    const totalScenes = Math.max(BASE_STORY_SCENE_COUNT, scenes.length || BASE_STORY_SCENE_COUNT)
    const timings: SceneTiming[] = []
    let currentTime = 0.0

    for (let i = 1; i <= totalScenes; i++) {
        const isHook = i <= 12
        const sceneData = scenes[i - 1] || {}

        let duration = getStandardSceneDuration(i)
        if (typeof sceneData.target_duration === 'number' && sceneData.target_duration > 0) {
            duration = sceneData.target_duration
        }

        const start = Math.round(currentTime * 10) / 10
        const end = Math.round((start + duration) * 10) / 10
        currentTime = end

        timings.push({
            scene_number: i,
            start_time: start,
            end_time: end,
            duration,
            is_video_required: isHook,
        })
    }

    return timings
}

export function splitTextToSingleLineChunks(
    text: string,
    maxChars: number = DEFAULT_SENIOR_SUBTITLE_MAX_CHARS
): string[] {
    if (!text || !text.trim()) return []
    const cleaned = text.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim()
    if (cleaned.length <= maxChars) return [cleaned]

    const words = cleaned.split(' ')
    const chunks: string[] = []
    let current = ''

    for (const word of words) {
        const candidate = current ? `${current} ${word}` : word

        if (candidate.length > maxChars) {
            if (current) {
                chunks.push(current.trim())
                current = word
            } else {
                chunks.push(word.slice(0, maxChars))
                current = word.slice(maxChars)
            }
        } else {
            current = candidate
        }
    }
    if (current.trim()) chunks.push(current.trim())

    return chunks
}

export function partitionScriptTo53Scenes(rawScriptText: string, totalScenesCount: number = BASE_STORY_SCENE_COUNT): string[] {
    const fullText = normalizedScriptText(rawScriptText)
    if (!fullText) {
        return Array.from({ length: totalScenesCount }, (_, i) => `Scene ${i + 1} narration`)
    }

    const durations = Array.from({ length: totalScenesCount }, (_, i) => getStandardSceneDuration(i + 1))
    const budgets = durations.map(readingBudgetForDuration)
    const result: string[] = []
    let charCursor = 0

    for (let i = 0; i < totalScenesCount; i++) {
        if (charCursor >= fullText.length) {
            result.push('')
            continue
        }

        const remainingText = fullText.length - charCursor
        if (i === totalScenesCount - 1) {
            result.push(fullText.slice(charCursor).trim())
            break
        }

        const maxForThisScene = Math.max(1, Math.min(budgets[i], remainingText))
        const hardLimit = Math.min(fullText.length, charCursor + maxForThisScene)
        const nextCursor = findNaturalCut(fullText, charCursor, hardLimit)

        result.push(fullText.slice(charCursor, nextCursor).trim())
        charCursor = nextCursor
    }

    while (result.length < totalScenesCount) result.push('')
    return result
}

export function partitionScriptByExistingSceneBoundaries(
    rawScriptText: string,
    scenes: any[],
    totalScenesCount: number = BASE_STORY_SCENE_COUNT
): string[] {
    const fullText = normalizedScriptText(rawScriptText)
    if (!fullText) {
        return Array.from({ length: totalScenesCount }, (_, i) => sceneNarrationText(scenes?.[i]) || `Scene ${i + 1} narration`)
    }

    const normalizedScenes = Array.from({ length: totalScenesCount }, (_, i) => scenes?.[i] || {})
    const existingLengths = normalizedScenes.map(scene => sceneNarrationText(scene).length)
    const hasUsefulBoundaries = existingLengths.filter(length => length > 0).length >= Math.min(3, totalScenesCount)
    const weights = hasUsefulBoundaries
        ? existingLengths.map((length, index) => Math.max(length, readingBudgetForDuration(getStandardSceneDuration(index + 1))))
        : Array.from({ length: totalScenesCount }, (_, i) => readingBudgetForDuration(getStandardSceneDuration(i + 1)))
    const totalWeight = weights.reduce((sum, weight) => sum + weight, 0) || fullText.length || 1
    const result: string[] = []
    let charCursor = 0
    let weightCursor = 0
    const anchorTextForScene = (scene: any): string => {
        const text = normalizedScriptText(sceneNarrationText(scene))
        if (!text) return ''
        return text.length <= 32 ? text : text.slice(0, 32)
    }

    for (let i = 0; i < totalScenesCount; i++) {
        if (charCursor >= fullText.length) {
            result.push('')
            continue
        }
        if (i === totalScenesCount - 1) {
            result.push(fullText.slice(charCursor).trim())
            break
        }

        const nextAnchor = anchorTextForScene(normalizedScenes[i + 1])
        if (hasUsefulBoundaries && nextAnchor.length >= 8) {
            const anchorPos = fullText.indexOf(nextAnchor, charCursor)
            if (anchorPos >= charCursor) {
                result.push(fullText.slice(charCursor, anchorPos).trim())
                charCursor = anchorPos
                weightCursor += weights[i]
                continue
            }
        }

        weightCursor += weights[i]
        const proportionalTarget = Math.round((weightCursor / totalWeight) * fullText.length)
        const hardLimit = Math.max(charCursor + 1, Math.min(fullText.length, proportionalTarget))
        const nextCursor = findNaturalCut(fullText, charCursor, hardLimit)
        result.push(fullText.slice(charCursor, nextCursor).trim())
        charCursor = nextCursor
    }

    while (result.length < totalScenesCount) result.push('')
    return result
}

export function generateSynchronizedSubtitles(
    rawScriptText: string,
    scenes: any[],
    maxCharsPerSub: number = DEFAULT_SENIOR_SUBTITLE_MAX_CHARS
): StdSubtitleItem[] {
    const totalScenes = estimateRequiredSceneCount(rawScriptText, scenes.length)
    const normalizedScenes = Array.from({ length: totalScenes }, (_, i) => scenes[i] || {
        scene_number: i + 1,
        visual_type: i < 12 ? 'video' : 'image',
        image_url: '',
        video_url: null,
    })
    const sceneTimings = calculateLongformSceneTimings(normalizedScenes)
    const partitionedScenes = partitionScriptByExistingSceneBoundaries(rawScriptText, normalizedScenes, totalScenes)

    const subtitles: StdSubtitleItem[] = []

    for (let sNum = 1; sNum <= totalScenes; sNum++) {
        const timing = sceneTimings[sNum - 1]
        const sceneData = normalizedScenes[sNum - 1] || {}
        const isHook = sNum <= 12

        let pureText = cleanKoreanScriptLine(partitionedScenes[sNum - 1] || sceneNarrationText(sceneData))
        if (!pureText || pureText.length < 2) {
            pureText = cleanKoreanScriptLine(sceneNarrationText(sceneData) || `Scene ${sNum} narration`)
        }

        const chunks = splitTextToSingleLineChunks(pureText, maxCharsPerSub)
        const chunkCount = Math.max(1, chunks.length)
        const sceneDuration = timing.duration || getStandardSceneDuration(sNum)
        const chunkDuration = Math.round((sceneDuration / chunkCount) * 10) / 10

        chunks.forEach((chunkText, cIdx) => {
            const subStart = Math.round((timing.start_time + cIdx * chunkDuration) * 10) / 10
            const subEnd = cIdx === chunks.length - 1
                ? timing.end_time
                : Math.round((subStart + chunkDuration) * 10) / 10

            subtitles.push({
                id: `sub-${sNum}-${cIdx + 1}`,
                scene_number: sNum,
                start_time: subStart.toFixed(1),
                end_time: subEnd.toFixed(1),
                start_num: subStart,
                end_num: subEnd,
                text: chunkText,
                image_url: sceneData.image_url || '',
                video_url: sceneData.video_url,
                is_hook_zone: isHook,
            })
        })
    }

    return subtitles
}
