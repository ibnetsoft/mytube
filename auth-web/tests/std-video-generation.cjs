const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
function load(name) {
    const file = path.resolve(__dirname, '../lib', name + '.ts')
    const exports = {}
    const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText
    new Function('exports', 'require', js)(exports, id => id.endsWith('.json') ? require(path.resolve(path.dirname(file), id)) : load(path.basename(id)))
    return exports
}
const { sceneVideoGeneration, videoPromptWithRatio, videoRatioLabels } = load('stdVideoGeneration')
const project = layout => ({project_payload: {render_settings: {comic: {version: 1, mode: 'moving_comic', layout}}}})
assert.equal(sceneVideoGeneration({}, 0).label, '16:9')
assert.equal(sceneVideoGeneration(project('spread'), 0).label, '1:1')
assert.equal(sceneVideoGeneration(project('grid'), 3).label, '16:9')
assert.equal(sceneVideoGeneration(project('inset'), 0).label, '16:9')
assert.equal(sceneVideoGeneration(project('inset'), 1).label, '4:3')
assert.equal(sceneVideoGeneration(project('inset'), 3).label, '4:3')
const spec = sceneVideoGeneration(project('inset'), 1)
const prompt = videoPromptWithRatio('Camera pans. Aspect ratio: 16:9. --ar 9:16 At 00:05 she smiles.', spec)
assert.match(prompt, /Aspect ratio: 4:3 \(width:height\)/)
assert.ok(!prompt.includes('16:9') && !prompt.includes('9:16'))
assert.match(prompt, /00:05 she smiles/)
assert.match(prompt, /one rectangular scene clip/)
assert.equal(videoPromptWithRatio(prompt, spec), prompt)
const changed = videoPromptWithRatio(prompt, sceneVideoGeneration({}, 0))
assert.match(changed, /Aspect ratio: 16:9/)
assert.ok(!changed.includes('4:3'))
assert.match(videoRatioLabels('th').title, /อัตราส่วน/)
console.log('PASS: standard ratio, physical panel ratios, inset scene order, stale ratio replacement, idempotent copying, Thai labels')

for (const locale of ['ko', 'en', 'vi', 'th']) {
    const labels = videoRatioLabels(locale)
    assert.ok(Object.values(labels).every(text => text && !text.startsWith('video_ratio_')))
    assert.equal(/[\u0E00-\u0E7F]/.test(Object.values(labels).join(' ')), locale === 'th')
}
assert.match(videoRatioLabels('vi').title, /Tỷ lệ/)
assert.equal(new Set(['ko', 'en', 'vi', 'th'].map(locale => videoRatioLabels(locale).title)).size, 4)
console.log('PASS: Korean, English, Vietnamese and Thai use their selected translation only')

const mixed = project('spread')
mixed.project_payload.render_settings.comic.page_layouts = {'0': 'single', '1': 'inset'}
assert.equal(sceneVideoGeneration(mixed, 0).label, '16:9')
assert.equal(sceneVideoGeneration(mixed, 1).label, '16:9')
assert.equal(sceneVideoGeneration(mixed, 2).label, '4:3')
assert.equal(sceneVideoGeneration(mixed, 3).label, '1:1')
console.log('PASS: per-page layouts use the actual panel slot across variable page sizes')
