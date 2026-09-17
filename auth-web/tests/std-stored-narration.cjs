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

    // MPEG1 layer III, 128 kbps, 44.1 kHz mono, with a per-file Info frame.
    const seek = Buffer.alloc(417); seek.set([0xff, 0xfb, 0x90, 0xc0]); seek.write('Info', 21)
    const frame = Buffer.alloc(417, 7); frame.set([0xff, 0xfb, 0x90, 0xc0])
    const id3 = Buffer.from([73,68,51,4,0,0,0,0,0,0])
    const id3v1 = Buffer.alloc(128); id3v1.write('TAG')
    const clip = Buffer.concat([id3, seek, frame, id3v1])
    assert.deepEqual(mp3.joinMp3Segments([clip, clip]), Buffer.concat([frame, frame]))
    console.log('PASS: ordered assembly, repeated clip reuse, retry reuse, MP3 per-clip metadata removal')
})().catch(e => { console.error(e); process.exit(1) })
