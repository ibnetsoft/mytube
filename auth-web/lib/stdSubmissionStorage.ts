/** Storage operations during submission must finish before the browser's deadline.
 * Keep the signal active while consuming the response, not only until headers arrive. */
export async function submissionStorageRequest(url: string, init: RequestInit, parent: AbortSignal, timeoutMs = 30000) {
    const signal = AbortSignal.any([parent, AbortSignal.timeout(timeoutMs)])
    try {
        const response = await fetch(url, { ...init, cache: 'no-store', signal })
        if (!response.ok) throw new Error(`저장소 응답 오류 (HTTP ${response.status})`)
        await response.arrayBuffer()
        return { headers: response.headers }
    } catch (error) {
        if (signal.aborted) throw new Error('저장소 응답 시간이 초과되었습니다. 제출은 접수되지 않았으므로 원본을 확인하고 다시 시도해 주세요.')
        throw error
    }
}
