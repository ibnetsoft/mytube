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

// 1. 영어 프롬프트 및 시스템 지시문 필터링 (순수 한국어 나레이션만 추출)
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
        .trim()

    // 영문 전용 프롬프트인 경우 제거
    if (/^[A-Za-z0-9\s\,\.\?\!\'\"\-:;]+$/.test(cleaned) && !/[가-힣]/.test(cleaned)) {
        return ''
    }

    const match = cleaned.match(/[가-힣0-9\s\,\.\?\!\'\"~·]+/g)
    if (match) {
        return match.join('').replace(/\s+/g, ' ').trim()
    }
    return cleaned.trim()
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
            const charCount = text.replace(/\s/g, '').length || 32
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

// 3. 순수 대본 문장들을 씬별 타임라인 및 5초 경계선에 스냅 정렬하여 자막 생성
export function generateSynchronizedSubtitles(
    rawScriptText: string,
    scenes: any[],
    maxCharsPerSub: number = 25
): StdSubtitleItem[] {
    const sceneTimings = calculateLongformSceneTimings(scenes)
    const totalScenes = sceneTimings.length

    // 기본 대체 스토리 문장들 (대본이 비어있을 때 사용)
    const fallbackStories = [
        "서른 해, 정확히 30년 동안 한 번도 거르지 않고 국민연금을 납입해온 부부가 있습니다.",
        "그리고 오늘, 그들이 마주한 건 아주 낯익은 문구가 찍힌 통장 한 장입니다.",
        "검은 잉크로 또렷하게 인쇄된 항목, '국민연금'",
        "그 옆에 적힌 숫자가 화면에 잡힙니다. 부부는 아무 말도 하지 않습니다.",
        "30년 차 부부의 실제 국민연금 수령액, 과연 얼마일까요?",
        "우리가 꿈꾸던 안락한 노후와 현실의 간극은 얼마나 벌어져 있을까요?",
        "30년을 일하고 은퇴한 한 가장의 고백에서 이야기는 시작됩니다.",
        "젊은 날, 월급 통장에서 꼬박꼬박 떼어가던 연금 보험료를 보며 그는 믿었습니다.",
        "국가가 약속한 든든한 노후를 의심하지 않았습니다.",
        "하지만 막상 통장에 찍힌 수령액은 부부의 한 달 최저 생활비에도 미치지 못했습니다.",
        "남편은 허탈하게 웃었고, 아내는 조용히 가계부를 펼쳤습니다.",
        "이제부터 공개할 내역은 대한민국 평범한 30년 차 부부의 숨김없는 현실입니다.",
    ]

    const subtitles: StdSubtitleItem[] = []

    // 씬 1~12: 5.0초 고정 훅 구간 처리
    for (let sNum = 1; sNum <= 12; sNum++) {
        const timing = sceneTimings[sNum - 1]
        const sceneData = scenes[sNum - 1] || {}
        let pureText = cleanKoreanScriptLine(sceneData.script_excerpt || sceneData.scene_text || '')
        if (!pureText || pureText.length < 3) {
            pureText = fallbackStories[(sNum - 1) % fallbackStories.length]
        }

        // 5초 구간 내 1개 또는 2개 자막으로 분할
        if (pureText.length > maxCharsPerSub) {
            const mid = Math.floor(pureText.length / 2)
            let splitIdx = pureText.indexOf(' ', mid - 4)
            if (splitIdx === -1) splitIdx = mid

            const sub1 = pureText.slice(0, splitIdx).trim()
            const sub2 = pureText.slice(splitIdx).trim()

            subtitles.push({
                id: `sub-${sNum}-1`,
                scene_number: sNum,
                start_time: timing.start_time.toFixed(1),
                end_time: (timing.start_time + 2.5).toFixed(1),
                start_num: timing.start_time,
                end_num: timing.start_time + 2.5,
                text: sub1,
                image_url: sceneData.image_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
                video_url: sceneData.video_url,
                is_hook_zone: true,
            })

            subtitles.push({
                id: `sub-${sNum}-2`,
                scene_number: sNum,
                start_time: (timing.start_time + 2.5).toFixed(1),
                end_time: timing.end_time.toFixed(1),
                start_num: timing.start_time + 2.5,
                end_num: timing.end_time,
                text: sub2,
                image_url: sceneData.image_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
                video_url: sceneData.video_url,
                is_hook_zone: true,
            })
        } else {
            subtitles.push({
                id: `sub-${sNum}`,
                scene_number: sNum,
                start_time: timing.start_time.toFixed(1),
                end_time: timing.end_time.toFixed(1),
                start_num: timing.start_time,
                end_num: timing.end_time,
                text: pureText,
                image_url: sceneData.image_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
                video_url: sceneData.video_url,
                is_hook_zone: true,
            })
        }
    }

    // 씬 13~53: 본문 스토리 동적 런닝타임 구간 처리
    for (let sNum = 13; sNum <= totalScenes; sNum++) {
        const timing = sceneTimings[sNum - 1]
        const sceneData = scenes[sNum - 1] || {}
        let pureText = cleanKoreanScriptLine(sceneData.script_excerpt || sceneData.scene_text || '')
        if (!pureText || pureText.length < 3) {
            pureText = `씬 ${sNum}의 본문 스토리 나레이션이 자연스럽게 이어집니다.`
        }

        const sceneDuration = timing.duration
        const subCount = Math.max(1, Math.ceil(pureText.length / maxCharsPerSub))

        if (subCount > 1) {
            const partDuration = Math.round((sceneDuration / subCount) * 10) / 10
            const words = pureText.split(' ')
            let chunks: string[] = []
            let curr = ''

            words.forEach(w => {
                if ((curr + ' ' + w).length > maxCharsPerSub) {
                    if (curr) chunks.push(curr.trim())
                    curr = w
                } else {
                    curr = curr ? `${curr} ${w}` : w
                }
            })
            if (curr) chunks.push(curr.trim())

            chunks.forEach((chunkText, cIdx) => {
                const subStart = Math.round((timing.start_time + cIdx * partDuration) * 10) / 10
                const subEnd = cIdx === chunks.length - 1
                    ? timing.end_time
                    : Math.round((subStart + partDuration) * 10) / 10

                subtitles.push({
                    id: `sub-${sNum}-${cIdx + 1}`,
                    scene_number: sNum,
                    start_time: subStart.toFixed(1),
                    end_time: subEnd.toFixed(1),
                    start_num: subStart,
                    end_num: subEnd,
                    text: chunkText,
                    image_url: sceneData.image_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
                    video_url: sceneData.video_url,
                    is_hook_zone: false,
                })
            })
        } else {
            subtitles.push({
                id: `sub-${sNum}`,
                scene_number: sNum,
                start_time: timing.start_time.toFixed(1),
                end_time: timing.end_time.toFixed(1),
                start_num: timing.start_time,
                end_num: timing.end_time,
                text: pureText,
                image_url: sceneData.image_url || 'https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=800&auto=format&fit=crop&q=80',
                video_url: sceneData.video_url,
                is_hook_zone: false,
            })
        }
    }

    return subtitles
}
