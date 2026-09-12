/** Conservative, local suggestions. Suggestions never change text or voice assignments. */
export interface DialogueCandidate {
    start: number
    end: number
    reason: string
}

export function detectDialogueCandidates(items: readonly { text?: string }[]): Map<number, DialogueCandidate[]> {
    const ranges: { index: number; start: number; end: number }[] = []
    let text = ''
    items.forEach((item, index) => {
        if (index) text += ' '
        const start = text.length
        text += String(item.text || '')
        ranges.push({ index, start, end: text.length })
    })
    const result = new Map<number, DialogueCandidate[]>()
    // Full sentences are reconstructed before classification, independent of subtitle wrapping.
    const sentences = [...text.matchAll(/[^.!?。！？]+[.!?。！？]*\s*/g)]
    const speechCue = /(?:말했|답했|물었|외쳤|소리쳤|속삭였|대답했|덧붙였|되물었|부탁했|중얼거렸)(?:습니다|어요|다|지요|죠)[.!?]?$/
    const narrative = /(?:그는|그녀는|노인은|며느리는|사람들은)\s|(?:했습니다|하였습니다|였어요|었습니다|았다|었다|였다|했어요|했죠|했지요|했어)[.!?]?$|고\s*(?:말|생각|물|답)|(?:걸었|돌아섰|끄덕였|바라봤|웃었|울었|떠났|기다렸)(?:습니다|어요|다)/
    const spokenEnding = /(?:세요|시오|지요|나요|까요|거야|잖아|겠어|할게|해줘|하지마|마세요|있어요|없어요|이에요|예요|입니다|습니다|해요|돼요|야|니)[.!?]?$/
    const address = /^(?:어머니|아버지|엄마|아빠|할머니|할아버지|여보|얘야|선생님|나리|어르신)[,!\s]/
    let followingSpeech = 0
    for (const match of sentences) {
        const sentence = match[0].trim()
        if (speechCue.test(sentence)) {
            followingSpeech = 2
            continue
        }
        const explicitQuote = /["'“”‘’「」『』]/.test(sentence)
        const isNarrative = narrative.test(sentence)
        const contextual = followingSpeech > 0 && !isNarrative
        const directAddress = address.test(sentence) && spokenEnding.test(sentence)
        if (!explicitQuote && !isNarrative && (contextual || directAddress)) {
            const start = match.index! + match[0].indexOf(sentence)
            const end = start + sentence.length
            const reason = contextual ? '앞 문장의 발화 표현 뒤에 이어지는 말입니다.' : '상대를 부르는 표현과 대화체 어미가 있습니다.'
            for (const range of ranges) {
                const overlapStart = Math.max(start, range.start)
                const overlapEnd = Math.min(end, range.end)
                if (overlapEnd <= overlapStart) continue
                const candidates = result.get(range.index) || []
                candidates.push({ start: overlapStart - range.start, end: overlapEnd - range.start, reason })
                result.set(range.index, candidates)
            }
        }
        followingSpeech = isNarrative || explicitQuote ? 0 : Math.max(0, followingSpeech - 1)
    }
    return result
}
