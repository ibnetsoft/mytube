// Keep each authorized media response small; retry reads, never paid generation.
const AUDIO_CHUNK_BYTES = 2 * 1024 * 1024

export async function loadSavedTtsAudio(
    url: string,
    headers: HeadersInit,
    read: typeof fetch = fetch,
    wait: (ms: number) => Promise<void> = ms => new Promise(resolve => setTimeout(resolve, ms)),
): Promise<Blob> {
    const parts: Blob[] = []
    let offset = 0
    let total: number | undefined
    do {
        for (let attempt = 0; ; attempt++) {
            let retryable = true
            try {
                const requestHeaders = new Headers(headers)
                if (!url.startsWith('data:')) requestHeaders.set('Range', `bytes=${offset}-${offset + AUDIO_CHUNK_BYTES - 1}`)
                const response = await read(url, { headers: requestHeaders })
                if (!response.ok) {
                    retryable = [408, 429, 500, 502, 503, 504].includes(response.status)
                    await response.body?.cancel()
                    throw new Error(`Saved audio download failed (${response.status})`)
                }
                const blob = await response.blob()
                if (/^(text\/|application\/json)/i.test(blob.type)) {
                    retryable = false
                    throw new Error('Saved audio download returned an invalid audio file')
                }
                if (response.status === 206) {
                    const range = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('Content-Range') || '')
                    if (!range || Number(range[1]) !== offset || Number(range[2]) + 1 > Number(range[3])
                        || Number(range[2]) < offset || blob.size !== Number(range[2]) - offset + 1
                        || (total !== undefined && total !== Number(range[3]))) {
                        retryable = false
                        throw new Error('Saved audio download returned an invalid byte range')
                    }
                    total = Number(range[3])
                } else if (offset > 0) {
                    retryable = false
                    throw new Error('Saved audio download did not continue the requested byte range')
                } else {
                    total = blob.size
                }
                parts.push(blob)
                offset += blob.size
                break
            } catch (error) {
                if (!retryable || attempt >= 2) throw error
                await wait(500 * (attempt + 1))
            }
        }
    } while (offset < total!)
    const audio = new Blob(parts, { type: parts[0]?.type || 'audio/mpeg' })
    if (audio.size < 256) throw new Error('Saved audio download returned an empty audio file')
    return audio
}
