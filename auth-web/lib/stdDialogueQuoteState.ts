const DIALOGUE_QUOTE_OPEN_TO_CLOSE: Record<string, string> = {
    '"': '"',
    "'": "'",
    '“': '”',
    '‘': '’',
    '「': '」',
    '『': '』',
}

const DIALOGUE_CLOSING_QUOTES = new Set(Object.values(DIALOGUE_QUOTE_OPEN_TO_CLOSE))

const isWordQuote = (text: string, index: number) => {
    const char = text[index]
    if (char !== "'" && char !== '"') return false
    const prev = text[index - 1] || ''
    const next = text[index + 1] || ''
    return /[A-Za-z0-9]/.test(prev) && /[A-Za-z0-9]/.test(next)
}

const isLooseClosingQuote = (text: string, index: number) => {
    const char = text[index]
    if (char !== "'" && char !== '"') return false
    const prev = text[index - 1] || ''
    const next = text[index + 1] || ''
    return Boolean(prev && !/\s/.test(prev) && (!next || /\s/.test(next)))
}

const isRepeatedOpeningQuote = (text: string, index: number, expectedClose: string) => {
    const char = text[index]
    if ((char !== "'" && char !== '"') || char !== expectedClose || index <= 0) return false
    if (text[index - 1] !== char) return false
    return text.slice(0, index - 1).trim() === '' && text.slice(index + 1).trim() !== ''
}

export const scanDialogueQuoteState = (text: string, incomingClose = '') => {
    const value = String(text || '')
    let expectedClose = incomingClose
    let isDialogue = Boolean(incomingClose)

    for (let i = 0; i < value.length; i += 1) {
        const char = value[i]
        if (isWordQuote(value, i)) continue

        if (expectedClose) {
            isDialogue = true
            if (isRepeatedOpeningQuote(value, i, expectedClose)) continue
            if (char === expectedClose || DIALOGUE_CLOSING_QUOTES.has(char)) {
                expectedClose = ''
            }
            continue
        }

        const nextClose = DIALOGUE_QUOTE_OPEN_TO_CLOSE[char]
        if (nextClose) {
            isDialogue = true
            expectedClose = isLooseClosingQuote(value, i) ? '' : nextClose
        } else if (DIALOGUE_CLOSING_QUOTES.has(char)) {
            isDialogue = true
        }
    }

    return { isDialogue, nextClose: expectedClose }
}

