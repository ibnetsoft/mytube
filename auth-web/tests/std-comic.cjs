const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const cache = {}
function load(name) {
    const file = path.resolve(__dirname, '../lib', name + '.ts')
    if (cache[file]) return cache[file]
    const exports = {}; cache[file] = exports
    const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText
    new Function('exports', 'require', js)(exports, id => id.endsWith('.json') ? require(path.resolve(path.dirname(file), id)) : load(path.basename(id)))
    return exports
}
const comic = load('stdComic'), policy = load('stdPolicy'), steps = load('stdProjectStepStatus')
const standard = { project_payload: {} }
const book = { project_payload: {render_settings: {comic: {version: 1, mode: 'comic'}}} }
assert.equal(comic.isComicProject(standard), false)
assert.equal(comic.isComicProject({project_payload:{render_settings:{comic:{mode:'comic'}}}}), false)
assert.equal(policy.isStdRequiredVideoScene(1, standard), true)
assert.equal(policy.isStdRequiredVideoScene(13, standard), false)
assert.equal(policy.isStdRequiredVideoScene(1, book), false)
assert.equal(policy.isStdRequiredVideoScene(1), true)
assert.equal(comic.selectComicMedia('comic', 'image', 'video'), 'image')
assert.equal(comic.selectComicMedia('moving_comic', 'image', 'video'), 'video')
assert.equal(comic.selectComicMedia('standard', 'image', 'video'), 'video')
assert.equal(comic.selectComicMedia('comic', undefined, 'video'), 'video')
const cfg = comic.normalizeComicSettings({version:1, mode:'comic', layout:'__proto__', turn_duration:Infinity})
assert.equal(cfg.layout, 'spread'); assert.equal(cfg.turn_duration, .7)
assert.deepEqual(comic.comicPages([1,2,3], cfg), [[1,2],[3]])
const imgProject = {...book, project_payload: {...book.project_payload, scenes:[{scene_number:1,image_url:'image.png'}]}}
assert.equal(steps.summarizeStdProject(imgProject).isImageDone, true)
assert.equal(steps.summarizeStdProject({...imgProject, project_payload:{...imgProject.project_payload,render_settings:{}}}).isImageDone, false)
const times = comic.comicSceneTimings([{scene_number:1},{scene_number:2}], [{scene_number:1,start_time:0,end_time:2,text:'a'},{scene_number:2,start_time:2,end_time:4,text:'b'}])
assert.deepEqual(times.map(t=>[t.start,t.end]), [[0,2],[2,4]])
console.log('PASS: opt-in, legacy hook policy, media priority, page grouping, timing, project readiness')
