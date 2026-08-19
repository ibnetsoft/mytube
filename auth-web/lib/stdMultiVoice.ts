/**
 * 롱폼 대본 멀티 보이스 (화자별 다중 성우) 분리 파싱 엔진
 */

export interface ScriptVoiceSegment {
    speaker: string
    text: string
    is_dialogue: boolean
}

export interface MultiVoiceParseResult {
    segments: ScriptVoiceSegment[]
    uniqueSpeakers: string[]
}

/**
 * 연출용 지문 괄호 제거 (예: "(한숨을 쉬며)", "[놀란 표정으로]")
 */
export function cleanActingDirections(text: string): string {
    if (!text) return ''
    return text
        .replace(/\([^\)]*\)/g, ' ')
        .replace(/\[[^\]]*\]/g, ' ')
        .replace(/\{[^\}]*\}/g, ' ')
        .replace(/[ \t]+/g, ' ')
        .trim()
}

/**
 * 대본을 한 줄씩 분석하여 나레이터 및 등장인물(화자)별 세그먼트로 파싱
 */
export function parseScriptToVoiceSegments(rawScript: string): MultiVoiceParseResult {
    if (!rawScript || !rawScript.trim()) {
        return { segments: [], uniqueSpeakers: [] }
    }

    const lines = rawScript.split(/\r?\n/)
    const rawSegments: ScriptVoiceSegment[] = []
    const speakerSet = new Set<string>()

    // 화자 인식 정규식 패턴: "할머니: 대사", "할머니) 대사", "[할머니] 대사"
    const speakerPrefixPattern = /^\s*[\*\_\[\(]*([^\s:：\)\]\(\*\_]{1,15})[\*\_\]\)]*[ \t]*(?:\([^)]*\))?[ \t]*[:：\)]([ \t]*)(.*)/

    let currentSpeaker = '나레이터'

    for (const rawLine of lines) {
        const line = rawLine.trim()
        if (!line) continue

        // 1. "화자: 대사" 또는 "화자) 대사" 형태 확인
        const match = line.match(speakerPrefixPattern)
        if (match) {
            let detectedSpeaker = match[1].trim().replace(/[\*\_\#\[\]\(\)]/g, '')
            const dialogueText = match[3].trim()

            // 불필요한 단어나 씬 번호(Scene 1 등) 필터링
            if (/^(씬|scene|챕터|chapter|part|제목|title)/i.test(detectedSpeaker)) {
                detectedSpeaker = '나레이터'
            }

            if (detectedSpeaker !== '나레이터') {
                speakerSet.add(detectedSpeaker)
            }

            const cleanedText = cleanActingDirections(dialogueText)
            if (cleanedText) {
                rawSegments.push({
                    speaker: detectedSpeaker,
                    text: cleanedText,
                    is_dialogue: detectedSpeaker !== '나레이터',
                })
            }
            currentSpeaker = '나레이터'
            continue
        }

        // 2. 큰따옴표("") 대사가 포함된 서술문 줄 파싱
        // 예: 그 말을 들은 할머니는 고개를 끄덕였어요. "그 집은 말이야, 대대로..."
        if (line.includes('"') || line.includes('“') || line.includes('”')) {
            const parts = line.split(/(["“][^"”]+["”])/g)
            for (const part of parts) {
                const trimmed = part.trim()
                if (!trimmed) continue

                if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith('“') && trimmed.endsWith('”'))) {
                    // 따옴표 내부 대사 (등장인물 화자)
                    const dialogueOnly = trimmed.replace(/^["“]|["”]$/g, '').trim()
                    const cleaned = cleanActingDirections(dialogueOnly)
                    if (cleaned) {
                        const targetSpeaker = currentSpeaker !== '나레이터' ? currentSpeaker : '화자1'
                        speakerSet.add(targetSpeaker)
                        rawSegments.push({
                            speaker: targetSpeaker,
                            text: cleaned,
                            is_dialogue: true,
                        })
                    }
                } else {
                    // 서술문 (나레이터)
                    const cleaned = cleanActingDirections(trimmed)
                    if (cleaned) {
                        rawSegments.push({
                            speaker: '나레이터',
                            text: cleaned,
                            is_dialogue: false,
                        })
                    }
                }
            }
            continue
        }

        // 3. 일반 서술문 (나레이터)
        const cleaned = cleanActingDirections(line)
        if (cleaned) {
            rawSegments.push({
                speaker: '나레이터',
                text: cleaned,
                is_dialogue: false,
            })
        }
    }

    // 연속된 동일 화자의 세그먼트는 하나로 병합하여 TTS 호출 횟수 최적화
    const mergedSegments: ScriptVoiceSegment[] = []
    for (const seg of rawSegments) {
        if (!seg.text) continue
        const last = mergedSegments[mergedSegments.length - 1]
        if (last && last.speaker === seg.speaker) {
            last.text += '\n' + seg.text
        } else {
            mergedSegments.push({ ...seg })
        }
    }

    return {
        segments: mergedSegments,
        uniqueSpeakers: Array.from(speakerSet),
    }
}
