/**
 * 롱폼 씬 타이밍 및 자막 3중 싱크 동기화 엔진
 * - 구역 1 (씬 1~12): 초반 1분 훅 구간 (정확히 5초씩 12개 비디오 씬 = 총 60초 고정)
 * - 구역 2 (씬 13~53): 본문 스토리 챕터별 동적 런닝타임 (글자수 비례 6.0s ~ 15.0s)
 */

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

// 1. 영어 프롬프트 및 시스템 지시문 필터링 (순수 한국어 나레이션만 추출 & 단일 행 정제)
export function cleanKoreanScriptLine(text: string): string {
    if (!text) return ''
    let cleaned = String(text)
        .replace(/First-minute micro beat.*?:/gi, '')
        .replace(/Keep this as a separate.*?hook:/gi, '')
        .replace(/The shot uses.*?photorealism\./gi, '')
        .replace(/Cinematic.*?8k/gi, '')
        .replace(/At the funeral hall.*?:/gi, '')
        .replace(/Scene \d+.*?:/gi, '')
        .replace(/\[Scene \d+\]/gi, '')
        .replace(/[\r\n]+/g, ' ')
        .trim()

    // 영문 전용 프롬프트인 경우 제거
    if (/^[A-Za-z0-9\s\,\.\?\!\'\"\-:;]+$/.test(cleaned) && !/[가-힣]/.test(cleaned)) {
        return ''
    }

    const match = cleaned.match(/[가-힣0-9\s\,\.\?\!\'\"~·]+/g)
    if (match) {
        return match.join('').replace(/\s+/g, ' ').trim()
    }
    return cleaned.replace(/\s+/g, ' ').trim()
}

/**
 * 롱폼 씬별 표준 런닝타임 (초) 규칙 (PACING_PHASES 규격)
 * - 1~12씬 (0~1분, Hook 훅 구간): 5.0초 고정 (12개 씬 × 5s = 60s)
 * - 13~28씬 (1~5분, Development 전개 구간): 15.0초 고정 (16개 씬 × 15s = 240s)
 * - 29~43씬 (5~10분, Explanation/Conflict 심화 구간): 20.0초 고정 (15개 씬 × 20s = 300s)
 * - 44~53씬 (10~15분, Climax/Ending 결말 구간): 30.0초 고정 (10개 씬 × 30s = 300s)
 * - 54씬 이후 (15분 초과 확장 구간): 60.0초 고정 (1분당 1개 씬)
 */
export function getStandardSceneDuration(sceneNumber: number): number {
    if (sceneNumber <= 12) return 5.0
    if (sceneNumber <= 28) return 15.0
    if (sceneNumber <= 43) return 20.0
    if (sceneNumber <= 53) return 30.0
    return 60.0 // 54씬부터는 무조건 1분(60초) 고정
}

// 2. 전체 53개 씬의 타임코드 경계선(Scene Timings) 계산
export function calculateLongformSceneTimings(scenes: any[]): SceneTiming[] {
    const totalScenes = Math.max(53, scenes.length || 53)
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

// 3. 한국어 어절 및 조사, 구두점 기반 지능형 1줄 청크 분할 유틸리티 (14~18자 내외)
export function splitTextToSingleLineChunks(text: string, maxChars: number = 18): string[] {
    if (!text || !text.trim()) return []
    const cleaned = text.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim()
    if (cleaned.length <= maxChars) return [cleaned]

    const words = cleaned.split(' ')
    const chunks: string[] = []
    let current = ''

    for (let i = 0; i < words.length; i++) {
        const word = words[i]
        const candidate = current ? `${current} ${word}` : word

        if (candidate.length > maxChars) {
            if (current) {
                chunks.push(current.trim())
                current = word
            } else {
                // 단어 자체가 너무 긴 경우 강제 분할
                chunks.push(word.slice(0, maxChars))
                current = word.slice(maxChars)
            }
        } else {
            current = candidate
        }
    }
    if (current.trim()) {
        chunks.push(current.trim())
    }

    return chunks
}

// 4. 전체 대본을 씬별 지속시간(5s, 15s, 20s, 30s)에 비례하여 지능형으로 분할 매핑하는 유틸리티
export function partitionScriptTo53Scenes(rawScriptText: string, totalScenesCount: number = 53): string[] {
    if (!rawScriptText || !rawScriptText.trim()) {
        return Array.from({ length: totalScenesCount }, (_, i) => `씬 ${i + 1} 나레이션`)
    }

    const cleanLines = rawScriptText
        .split('\n')
        .map(l => l.trim())
        .filter(l => l.length > 0)
        // 화자 태그 (진행자1:, 나레이터: 등) 정제
        .map(l => l.replace(/^(?:진행자\d+|나레이터|화자\d+|호스트|해설자|Speaker\s*\d+)\s*[:：]\s*/i, '').trim())
        .filter(l => l.length > 0)

    if (cleanLines.length === 0) {
        return Array.from({ length: totalScenesCount }, (_, i) => `씬 ${i + 1} 나레이션`)
    }

    // 전체 대본 텍스트를 문장 단위로 분할
    const fullText = cleanLines.join(' ')
    const sentences = fullText.match(/[^.!?]+[.!?]+/g) || fullText.split('\n')
    const cleanedSentences = sentences.map(s => s.trim()).filter(s => s.length > 0)

    const durations = Array.from({ length: totalScenesCount }, (_, i) => getStandardSceneDuration(i + 1))

    if (cleanedSentences.length >= totalScenesCount) {
        const result: string[] = []
        let sentCursor = 0
        const totalSents = cleanedSentences.length

        for (let i = 0; i < totalScenesCount; i++) {
            if (i === totalScenesCount - 1) {
                result.push(cleanedSentences.slice(sentCursor).join(' ').trim())
                break
            }

            const remainingScenes = totalScenesCount - i
            const remainingSents = totalSents - sentCursor
            const remainingDuration = durations.slice(i).reduce((a, b) => a + b, 0)
            const weight = durations[i] / (remainingDuration || 1)

            const allocatedSents = Math.max(
                1,
                Math.min(remainingSents - (remainingScenes - 1), Math.round(remainingSents * weight))
            )

            const chunk = cleanedSentences.slice(sentCursor, sentCursor + allocatedSents)
            result.push(chunk.join(' ').trim())
            sentCursor += allocatedSents
        }
        return result
    }

    // 문장 수가 씬 수보다 적으면 글자수를 씬 지속시간 비율에 맞춰 분할
    const totalChars = fullText.length
    const result: string[] = []
    let charCursor = 0

    for (let i = 0; i < totalScenesCount; i++) {
        if (i === totalScenesCount - 1) {
            result.push(fullText.slice(charCursor).trim())
            break
        }

        const remainingScenes = totalScenesCount - i
        const remainingChars = totalChars - charCursor
        const remainingDuration = durations.slice(i).reduce((a, b) => a + b, 0)
        const weight = durations[i] / (remainingDuration || 1)

        const allocatedChars = Math.max(
            15,
            Math.min(remainingChars - (remainingScenes - 1) * 15, Math.round(remainingChars * weight))
        )

        let nextCursor = charCursor + allocatedChars
        const spaceIdx = fullText.indexOf(' ', nextCursor - 6)
        if (spaceIdx !== -1 && spaceIdx < nextCursor + 12) {
            nextCursor = spaceIdx + 1
        }

        result.push(fullText.slice(charCursor, nextCursor).trim())
        charCursor = nextCursor
    }
    return result
}

// 5. 전체 대본을 잘게 나누어 씬별 타임라인과 1:1로 매칭되는 1줄 자막 목록 생성
export function generateSynchronizedSubtitles(
    rawScriptText: string,
    scenes: any[],
    maxCharsPerSub: number = 18
): StdSubtitleItem[] {
    const sceneTimings = calculateLongformSceneTimings(scenes)
    const totalScenes = sceneTimings.length
    const partitionedScenes = partitionScriptTo53Scenes(rawScriptText, totalScenes)

    const subtitles: StdSubtitleItem[] = []

    for (let sNum = 1; sNum <= totalScenes; sNum++) {
        const timing = sceneTimings[sNum - 1]
        const sceneData = scenes[sNum - 1] || {}
        const isHook = sNum <= 12

        // rawScriptText에서 분할된 텍스트가 있으면 최우선 적용, 없으면 sceneData fallback
        let pureText = cleanKoreanScriptLine(partitionedScenes[sNum - 1] || sceneData.script_excerpt || sceneData.scene_text || sceneData.text || '')
        if (!pureText || pureText.length < 2) {
            pureText = cleanKoreanScriptLine(sceneData.script_excerpt || sceneData.scene_text || sceneData.text || `씬 ${sNum} 나레이션`)
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
