import { joinMp3Segments } from './stdJoinMp3'

type Segment = { text: string; voiceId: string; direction?: string }
type Resolved = { asset: any; cached: boolean }

// Resolve and read existing recordings before spending anything on missing ones.
// Persisting each missing recording happens in resolve, using the preview cache/claim.
export async function assembleStoredNarration(segments: Segment[], io: {
    resolve: (segment: Segment, index: number, cacheOnly: boolean) => Promise<Resolved | null>
    read: (asset: any) => Promise<Buffer>
}) {
    const deadline = Date.now() + 240_000
    const buffers: (Buffer | null)[] = []
    let reused = 0, generated = 0
    const checkTime = () => {
        if (Date.now() > deadline) throw new Error('음성 준비 시간이 길어져 중단했습니다. 저장+TTS를 다시 누르면 이미 저장된 조각부터 재사용합니다.')
    }
    let nextIndex = 0
    // Bound simultaneous DB/Storage reads for long projects while retaining subtitle order.
    await Promise.all(Array.from({ length: Math.min(4, segments.length) }, async () => {
        while (nextIndex < segments.length) {
            const index = nextIndex++
            checkTime()
            const found = await io.resolve(segments[index], index, true)
            const buffer = found ? await io.read(found.asset) : null
            if (buffer && !buffer.length) throw new Error('저장된 음성 파일이 비어 있습니다.')
            buffers[index] = buffer
            if (found) reused++
        }
    }))
    for (let index = 0; index < segments.length; index++) {
        if (buffers[index]) continue
        checkTime()
        const result = await io.resolve(segments[index], index, false)
        if (!result) throw new Error('구간 음성이 저장되지 않았습니다.')
        const buffer = await io.read(result.asset)
        if (!buffer.length) throw new Error('구간 음성 파일이 비어 있습니다.')
        buffers[index] = buffer
        if (result.cached) reused++
        else generated++
    }
    return { audioBuffer: joinMp3Segments(buffers as Buffer[]), reused, generated }
}
