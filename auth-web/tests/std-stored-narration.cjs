const fs = require('fs'), ts = require('typescript'), assert = require('node:assert/strict')
function load(file, deps = {}) {
    const exports = {}
    new Function('require', 'exports', ts.transpile(fs.readFileSync(file, 'utf8'), { module: 1, target: 7 }))(
        id => deps[id] || require(id), exports)
    return exports
}
const mp3 = load('auth-web/lib/stdJoinMp3.ts')
const { assembleStoredNarration } = load('auth-web/lib/stdStoredNarration.ts', { './stdJoinMp3': mp3 })
;(async () => {
    const saved = new Map([['first', Buffer.from('A')], ['last', Buffer.from('C')]])
    let generated = 0, fail = true
    const segments = ['first', 'missing', 'last', 'missing'].map(text => ({ text, voiceId: 'voice' }))
    const io = {
        resolve: async (s, index, cacheOnly) => {
            if (saved.has(s.text)) return { asset: s.text, cached: true }
            if (cacheOnly) return null
            if (fail) throw Error('provider failed')
            generated++; saved.set(s.text, Buffer.from('B'))
            return { asset: s.text, cached: false }
        },
        read: async key => saved.get(key),
    }
    await assert.rejects(assembleStoredNarration(segments, io), /provider failed/)
    fail = false
    const first = await assembleStoredNarration(segments, io)
    assert.equal(first.audioBuffer.toString(), 'ABCB')
    assert.equal(generated, 1, 'Repeated identical subtitles reuse the recording generated earlier in the same run')
    assert.deepEqual([first.reused, first.generated], [3, 1])
    await assembleStoredNarration(segments, io)
    assert.equal(generated, 1, 'Retry does not re-synthesize saved clips')

    let spend = 0, reads = 0
    const cacheFailure = {
        resolve: async (s, i, cacheOnly) => {
            if (!cacheOnly) spend++
            return s.text === 'missing' ? null : { asset: s.text, cached: true }
        },
        read: async () => { throw Error('storage unavailable') },
    }
    await assert.rejects(assembleStoredNarration(segments, cacheFailure), /storage unavailable/)
    assert.equal(spend, 0, 'Storage errors must never trigger paid regeneration')
    await assert.rejects(assembleStoredNarration(segments, {
        resolve: async (_, i, cacheOnly) => { if (!cacheOnly) spend++; return null },
        read: async () => Buffer.from('x'),
    }, { allowGenerate: false }), /준비된 구간/)
    assert.equal(spend, 0, 'Final join must only use prepared recordings')
    await assembleStoredNarration([segments[0], segments[0]], {
        resolve: async () => ({ asset: 'same', cached: true }),
        read: async () => { reads++; return Buffer.from('a') },
    })
    assert.equal(reads, 1, 'Identical recordings are downloaded once')

    const { generateNarrationInBatches, NARRATION_BATCH_SIZE } = load('auth-web/lib/stdNarrationBatch.ts')
    const long = Array.from({ length: 17 }, (_, i) => ({ text: String(i), voiceId: 'v' }))
    const originalNow = Date.now
    let now = 0, calls = 0
    let recordings = new Map()
    Date.now = () => now
    const slowIo = {
        resolve: async (s, i, cacheOnly) => {
            if (recordings.has(s.text)) return { asset: s.text, cached: true }
            if (cacheOnly) return null
            calls++
            // Simulate 100 seconds per parallel provider wave, without waiting.
            if (calls % 4 === 0) now += 100000
            recordings.set(s.text, Buffer.from(s.text + ','))
            return { asset: s.text, cached: false }
        },
        read: async asset => recordings.get(asset),
    }
    try {
        await assert.rejects(assembleStoredNarration(long, slowIo), /초과/)
        now = 0; calls = 0; recordings = new Map()
        const progress = [], sizes = []
        const result = await generateNarrationInBatches({ voice_segments: long }, async body => {
            const prepare = body.mode === 'prepare_narration_segments'
            if (prepare) sizes.push(body.voice_segments.length)
            const out = await assembleStoredNarration(body.voice_segments, slowIo, { allowGenerate: prepare })
            return { res: { ok: true, status: 200 }, payload: { success: true,
                prepared: prepare ? body.voice_segments.length : undefined,
                audio: out.audioBuffer.toString(), segment_reuse: { generated: out.generated, reused: out.reused } } }
        }, ready => progress.push(ready))
        assert(now > 270000, 'Total job exceeds old single-request deadline')
        assert(sizes.every(n => n <= NARRATION_BATCH_SIZE))
        assert.deepEqual(progress, [4, 8, 12, 16, 17])
        assert.equal(result.payload.audio, long.map(s => s.text + ',').join(''))
        assert.equal(calls, 17)
        assert.deepEqual(result.payload.segment_reuse, { generated: 17, reused: 0 })
    } finally { Date.now = originalNow }
    let requests = 0
    await assert.rejects(generateNarrationInBatches({ voice_segments: long }, async () => {
        requests++
        return { res: { ok: false, status: 409 }, payload: { error: 'generation claimed' } }
    }, () => {}), /generation claimed/)
    assert.equal(requests, 1, 'No final join or automatic paid retry after uncertain failure')

    // MPEG1 layer III, 128 kbps, 44.1 kHz mono, with a per-file Info frame.
    const seek = Buffer.alloc(417); seek.set([0xff, 0xfb, 0x90, 0xc0]); seek.write('Info', 21)
    const frame = Buffer.alloc(417, 7); frame.set([0xff, 0xfb, 0x90, 0xc0])
    const id3 = Buffer.from([73,68,51,4,0,0,0,0,0,0])
    const id3v1 = Buffer.alloc(128); id3v1.write('TAG')
    const clip = Buffer.concat([id3, seek, frame, id3v1])
    assert.deepEqual(mp3.joinMp3Segments([clip, clip]), Buffer.concat([frame, frame]))
    console.log('PASS: ordered assembly, retry reuse, no regeneration on read errors, batched long-job completion beyond 270 seconds, MP3 metadata removal')
})().catch(e => { console.error(e); process.exit(1) })
