import { joinMp3Segments, mp3FrameDuration } from './stdJoinMp3'

type Segment = { text: string; voiceId: string; direction?: string }
type Resolved = { asset: any; cached: boolean }

// Wait for active operations before returning an error, and stop scheduling more.
async function boundedWork(count: number, concurrency: number, work: (index: number) => Promise<void>) {
    let cursor = 0
    let failure: unknown
    await Promise.all(Array.from({ length: Math.min(concurrency, count) }, async () => {
        while (cursor < count && !failure) {
            const index = cursor++
            try { await work(index) } catch (error) { failure = failure || error }
        }
    }))
    if (failure) throw failure
}

// A missing cache entry permits generation; a failed lookup/download does not.
export async function assembleStoredNarration(segments: Segment[], io: {
    resolve: (segment: Segment, index: number, cacheOnly: boolean) => Promise<Resolved | null>
    read: (asset: any) => Promise<Buffer>
}, options: { allowGenerate?: boolean } = {}) {
    const deadline = Date.now() + 270_000
    const buffers: (Buffer | null)[] = Array(segments.length).fill(null)
    let reused = 0, generated = 0
    const checkTime = () => {
        if (Date.now() > deadline) throw new Error('저장된 음성 준비 시간이 초과되었습니다. 완료된 조각은 보존되어 다시 시도할 때 재사용됩니다.')
    }
    const key = (s: Segment) => JSON.stringify([s.voiceId, s.direction || '', s.text])
    const cached = new Map<string, Promise<Buffer | null>>()
    const read = async (asset: any) => {
        const buffer = await io.read(asset)
        if (!buffer?.length) throw new Error('저장된 구간 음성 파일이 비어 있습니다. 새 음성을 생성하지 않았습니다.')
        return buffer
    }
    await boundedWork(segments.length, 8, async index => {
        checkTime()
        const segment = segments[index], identity = key(segment)
        let task = cached.get(identity)
        if (!task) {
            task = io.resolve(segment, index, true).then(found => found ? read(found.asset) : null)
            cached.set(identity, task)
        }
        buffers[index] = await task
        if (buffers[index]) reused++
    })
    const missing = segments.map((_, index) => index).filter(index => !buffers[index])
    if (missing.length && options.allowGenerate === false) {
        throw new Error('준비된 구간 음성을 찾을 수 없습니다. 저장+TTS를 다시 누르면 누락된 조각만 준비합니다.')
    }
    const inFlight = new Map<string, Promise<{ buffer: Buffer; cached: boolean }>>()
    await boundedWork(missing.length, 4, async position => {
        checkTime()
        const index = missing[position], segment = segments[index], identity = key(segment)
        let task = inFlight.get(identity)
        const initiator = !task
        if (!task) {
            task = io.resolve(segment, index, false).then(async result => {
                if (!result) throw new Error('구간 음성이 저장되지 않았습니다.')
                return { buffer: await read(result.asset), cached: result.cached }
            })
            inFlight.set(identity, task)
        }
        const result = await task
        buffers[index] = result.buffer
        if (initiator && !result.cached) generated++
        else reused++
    })
    let elapsed = 0
    const frames = (buffers as Buffer[]).map(buffer => joinMp3Segments([buffer]))
    const timeline = frames.map((buffer, index) => {
        const start = elapsed
        elapsed += mp3FrameDuration(buffer)
        return { text: segments[index].text, voice_id: segments[index].voiceId, start, end: elapsed }
    })
    return { audioBuffer: Buffer.concat(frames), reused, generated, timeline }
}
