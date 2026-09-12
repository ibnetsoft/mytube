const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const path = require('node:path')
const compiled = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdTimingSync.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText
const api = {}
new Function('exports', compiled)(api)

async function main() {
    let active = 0, maxActive = 0
    const progress = []
    const durations = await api.measureSubtitleDurations([30, 5, 15, 1], async (delay, index) => {
        maxActive = Math.max(maxActive, ++active)
        await new Promise(resolve => setTimeout(resolve, delay))
        active--
        return index + 1
    }, new AbortController().signal, count => progress.push(count))
    assert.deepEqual(durations, [1, 2, 3, 4], 'completion order must not reorder subtitles')
    assert.equal(maxActive, 3)
    assert.deepEqual(progress, [1, 2, 3, 4])

    let stoppedSignal
    await assert.rejects(api.measureSubtitleDurations([1], (_, index, signal) => {
        stoppedSignal = signal
        return new Promise(() => {})
    }, new AbortController().signal, () => {}, 10), /응답 시간이 초과/)
    assert.equal(stoppedSignal.aborted, true)
    const controller = new AbortController()
    const pending = api.measureSubtitleDurations([1, 2, 3, 4], () => new Promise(() => {}), controller.signal, () => {})
    controller.abort(new Error('cancelled'))
    await assert.rejects(pending, /cancelled/)
    await assert.rejects(api.measureSubtitleDurations([1], async () => Infinity, new AbortController().signal, () => {}), /올바르지/)

    let audio
    global.Audio = class {
        constructor() { audio = this }
        removeAttribute() { this.removed = true }
        load() {}
    }
    const audioController = new AbortController()
    const measurement = api.readAudioDuration('test.mp3', audioController.signal)
    audioController.abort(new Error('cancelled'))
    await assert.rejects(measurement, /cancelled/)
    assert.equal(audio.removed, true)
    assert.equal(audio.onloadedmetadata, null)
    const ready = api.readAudioDuration('ready.mp3', new AbortController().signal)
    audio.duration = 2.5
    audio.onloadedmetadata()
    assert.equal(await ready, 2.5)
    console.log('PASS: bounded concurrency, ordering, hung request timeout, cancellation, invalid duration, audio cleanup')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
