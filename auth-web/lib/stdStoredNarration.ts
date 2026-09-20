import { joinMp3Segments } from './stdJoinMp3'

type Segment = { text: string; voiceId: string; direction?: string }
type Resolved = { asset: any; cached: boolean }

// Resolve and read existing recordings before spending anything on missing ones.
// Persisting each missing recording happens in resolve, using the preview cache/claim.
export async function assembleStoredNarration(segments: Segment[], io: {
    resolve: (segment: Segment, index: number, cacheOnly: boolean) => Promise<Resolved | null>
    read: (asset: any) => Promise<Buffer>
}) {
    const deadline = Date.now() + 270_000
    const buffers: (Buffer | null)[] = []
    let reused = 0, generated = 0
    const checkTime = () => {
        if (Date.now() > deadline) throw new Error('음성 준비 시간이 길어져 중단했습니다. 저장+TTS를 다시 누르면 이미 저장된 조각부터 재사용합니다.')
    }
    let nextIndex = 0
    // Bound simultaneous DB/Storage reads for long projects while retaining subtitle order.
    await Promise.all(Array.from({ length: Math.min(6, segments.length) }, async () => {
        while (nextIndex < segments.length) {
            const index = nextIndex++
            checkTime()
            let buffer: Buffer | null = null
            try {
                const found = await io.resolve(segments[index], index, true)
                if (found) {
                    try {
                        const readBuffer = await io.read(found.asset)
                        if (readBuffer && readBuffer.length > 0) {
                            buffer = readBuffer
                            reused++
                        }
                    } catch (readError) {
                        console.warn(`[assembleStoredNarration] cache read failed for index ${index}, will re-synthesize:`, readError)
                        buffer = null
                    }
                }
            } catch (resolveError) {
                console.warn(`[assembleStoredNarration] cache resolve failed for index ${index}, will re-synthesize:`, resolveError)
                buffer = null
            }
            buffers[index] = buffer
        }
    }))

    const missingIndexes: number[] = []
    for (let i = 0; i < segments.length; i++) {
        if (!buffers[i]) missingIndexes.push(i)
    }

    if (missingIndexes.length > 0) {
        const inFlight = new Map<string, Promise<{ asset: any; cached: boolean }>>()
        const concurrency = Math.min(5, missingIndexes.length)
        let missingCursor = 0

        await Promise.all(Array.from({ length: concurrency }, async () => {
            while (missingCursor < missingIndexes.length) {
                const index = missingIndexes[missingCursor++]
                checkTime()
                const seg = segments[index]
                const segKey = `${seg.voiceId}|${seg.direction || ''}|${seg.text}`

                let isInitiator = false
                let task = inFlight.get(segKey)
                if (!task) {
                    isInitiator = true
                    task = io.resolve(seg, index, false).then(res => {
                        if (!res) throw new Error('구간 음성이 저장되지 않았습니다.')
                        return res
                    })
                    inFlight.set(segKey, task)
                }

                const result = await task
                const buffer = await io.read(result.asset)
                if (!buffer || !buffer.length) throw new Error('구간 음성 파일이 비어 있습니다.')
                buffers[index] = buffer
                if (isInitiator && !result.cached) {
                    generated++
                } else {
                    reused++
                }
            }
        }))
    }

    return { audioBuffer: joinMp3Segments(buffers as Buffer[]), reused, generated }
}
