export function abortable<T>(work: Promise<T>, signal: AbortSignal): Promise<T> {
    return new Promise((resolve, reject) => {
        const onAbort = () => reject(signal.reason || new Error('작업이 취소되었습니다.'))
        // Attach handlers even when already aborted, so late rejection is consumed.
        work.then(value => {
            signal.removeEventListener('abort', onAbort)
            resolve(value)
        }, error => {
            signal.removeEventListener('abort', onAbort)
            reject(error)
        })
        if (signal.aborted) onAbort()
        else signal.addEventListener('abort', onAbort, { once: true })
    })
}

export async function measureSubtitleDurations<T>(
    items: readonly T[],
    measure: (item: T, index: number, signal: AbortSignal) => Promise<number>,
    signal: AbortSignal,
    onProgress: (completed: number) => void,
    timeoutMs = 60_000,
): Promise<number[]> {
    const controller = new AbortController()
    const cancel = () => controller.abort(signal.reason)
    signal.addEventListener('abort', cancel, { once: true })
    if (signal.aborted) cancel()
    const durations = new Array<number>(items.length)
    let next = 0
    let completed = 0
    const worker = async () => {
        while (next < items.length) {
            if (controller.signal.aborted) throw controller.signal.reason
            const index = next++
            const timer = setTimeout(() => controller.abort(new Error(`자막 ${index + 1}번 음성 응답 시간이 초과되었습니다. 다시 시도해 주세요.`)), timeoutMs)
            try {
                const duration = await abortable(measure(items[index], index, controller.signal), controller.signal)
                if (!Number.isFinite(duration) || duration <= 0) throw new Error(`자막 ${index + 1}번 음성 길이가 올바르지 않습니다.`)
                durations[index] = duration
                onProgress(++completed)
            } finally {
                clearTimeout(timer)
            }
        }
    }
    try {
        await Promise.all(Array.from({ length: Math.min(3, items.length) }, worker))
        return durations
    } catch (error) {
        controller.abort(error)
        throw error
    } finally {
        signal.removeEventListener('abort', cancel)
    }
}

export function readAudioDuration(url: string, signal: AbortSignal): Promise<number> {
    return new Promise((resolve, reject) => {
        const audio = new Audio()
        const cleanup = () => {
            clearTimeout(timer)
            signal.removeEventListener('abort', onAbort)
            audio.onloadedmetadata = null
            audio.onerror = null
            audio.removeAttribute('src')
            audio.load()
        }
        const fail = (error: unknown) => { cleanup(); reject(error) }
        const onAbort = () => fail(signal.reason || new Error('작업이 취소되었습니다.'))
        const timer = setTimeout(() => fail(new Error('음성 길이를 15초 안에 읽지 못했습니다.')), 15_000)
        signal.addEventListener('abort', onAbort, { once: true })
        if (signal.aborted) { onAbort(); return }
        audio.preload = 'metadata'
        audio.onloadedmetadata = () => {
            const duration = Number(audio.duration)
            cleanup()
            if (Number.isFinite(duration) && duration > 0) resolve(duration)
            else reject(new Error('음성 길이를 읽을 수 없습니다.'))
        }
        audio.onerror = () => fail(new Error('음성 파일을 읽지 못했습니다.'))
        audio.src = url
        audio.load()
    })
}
