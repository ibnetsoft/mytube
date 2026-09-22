const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const api = {}
new Function('exports', ts.transpile(fs.readFileSync(require.resolve('../lib/stdSpeechGain.ts'), 'utf8'), {module: 1, target: 7}))(api)
assert.equal(api.subtitleGain({volume: 200}), 2)
assert.equal(api.subtitleGain({volume_ratio: 0}), 0)
assert.equal(api.subtitleGain({volume: 0, volume_ratio: 2}), 0)
assert.equal(api.subtitleGain({volume: 'bad'}), 1)
assert.equal(api.speechNormalization([new Float32Array(100)]), 1)
const tone = amplitude => Float32Array.from({length: 48000}, (_, i) => amplitude * Math.sin(i * 2 * Math.PI * 440 / 48000))
const loud = tone(.24), quiet = tone(.06)
const ratio = api.speechNormalization([quiet]) / api.speechNormalization([loud])
assert.ok(Math.abs(ratio - 4) < .12, `quiet speaker correction: ${ratio}`)
let disconnected = 0
const gain = {gain: {value: 1}, connect() {return this}, disconnect() {disconnected++}}
const source = {connect() {return gain}, disconnect() {disconnected++}}
const graph = api.connectSpeechGain({createMediaElementSource: () => source, createGain: () => gain, destination: {}}, {})
graph.set(2)
assert.equal(gain.gain.value, 2, 'Web Audio supports amplification above 100%')
graph.set(0)
assert.equal(gain.gain.value, 0)
graph.dispose()
assert.equal(disconnected, 2)
const queue = fs.readFileSync(require.resolve('../lib/stdRenderQueue.ts'), 'utf8')
const section = queue.slice(queue.indexOf('function buildRenderSubtitles('), queue.indexOf('function sentenceComplete('))
const build = new Function('subtitleGain', ts.transpile(section + '\nreturn buildRenderSubtitles', {module: 1, target: 7}))(api.subtitleGain)
const rendered = build({project_payload: {subtitles: [
    {text: 'loud', start: 0, end: 1, volume: 200},
    {text: 'mute', start: 1, end: 2, volume_ratio: 0},
]}}, [])
assert.equal(rendered[0].volume, 200)
assert.equal(rendered[1].volume, 0)
console.log('PASS: speech balancing, 200% amplification, mute, graph cleanup')
