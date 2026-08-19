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

// 2. 전체 53개 씬의 타임코드 경계선(Scene Timings) 계산
export function calculateLongformSceneTimings(scenes: any[]): SceneTiming[] {
    const totalScenes = Math.max(53, scenes.length || 53)
    const timings: SceneTiming[] = []
    let currentTime = 0.0

    for (let i = 1; i <= totalScenes; i++) {
        let duration = 5.0
        const isHook = i <= 12

        if (isHook) {
            // 씬 1~12: 초반 1분 훅 구간 (정확히 5.0초 고정)
            duration = 5.0
        } else {
            // 씬 13~53: 대본 글자수에 비례한 동적 런닝타임 (6.0s ~ 15.0s)
            const sceneData = scenes[i - 1] || {}
            const text = cleanKoreanScriptLine(sceneData.script_excerpt || sceneData.scene_text || sceneData.prompt_ko || '')
            const charCount = text.replace(/\s/g, '').length || 30
            duration = Math.max(6.0, Math.min(15.0, Math.round((charCount * 0.22 + 1.2) * 10) / 10))
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

// 4. 전체 대본을 잘게 나누어 씬별 타임라인과 1:1로 매칭되는 1줄 자막 목록 생성
export function generateSynchronizedSubtitles(
    rawScriptText: string,
    scenes: any[],
    maxCharsPerSub: number = 18
): StdSubtitleItem[] {
    const sceneTimings = calculateLongformSceneTimings(scenes)
    const totalScenes = sceneTimings.length

    const fallbackStories = [
        "서른 해 동안",
        "한 번도 거르지 않고",
        "국민연금을 성실히 납입해온",
        "평범한 부부가 있습니다.",
        "그리고 오늘, 그들이 마주한",
        "통장 한 장이 있습니다.",
        "검은 잉크로 인쇄된",
        "'국민연금' 항목 옆에",
        "적힌 숫자를 보며",
        "부부는 아무 말도 못 합니다.",
        "30년 차 부부의 실제 수령액,",
        "과연 얼마였을까요?",
    ]

    const subtitles: StdSubtitleItem[] = []

    // 씬 1~12: 5.0초 고정 훅 구간 처리 (씬당 2~3개의 1줄 자막으로 잘게 분할)
    for (let sNum = 1; sNum <= 12; sNum++) {
        const timing = sceneTimings[sNum - 1]
        const sceneData = scenes[sNum - 1] || {}
        let pureText = cleanKoreanScriptLine(sceneData.script_excerpt || sceneData.scene_text || '')
        if (!pureText || pureText.length < 3) {
            pureText = fallbackStories[(sNum - 1) % fallbackStories.length]
        }

        const chunks = splitTextToSingleLineChunks(pureText, maxCharsPerSub)
        const chunkCount = Math.max(1, chunks.length)
        const chunkDuration = Math.round((5.0 / chunkCount) * 10) / 10

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
                is_hook_zone: true,
            })
        })
    }

    // 씬 13~53: 본문 스토리 동적 런닝타임 구간 처리 (씬당 3~6개의 1줄 자막으로 잘게 분할)
    for (let sNum = 13; sNum <= totalScenes; sNum++) {
        const timing = sceneTimings[sNum - 1]
        const sceneData = scenes[sNum - 1] || {}
        let pureText = cleanKoreanScriptLine(sceneData.script_excerpt || sceneData.scene_text || '')
        if (!pureText || pureText.length < 3) {
            pureText = `씬 ${sNum}의 본문 스토리 나레이션이 자연스럽게 이어집니다.`
        }

        const chunks = splitTextToSingleLineChunks(pureText, maxCharsPerSub)
        const chunkCount = Math.max(1, chunks.length)
        const sceneDuration = timing.duration
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
                is_hook_zone: false,
            })
        })
    }

    return subtitles
}
