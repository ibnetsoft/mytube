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

const mixed=comic.normalizeComicSettings({version:1,mode:'moving_comic',layout:'grid',page_layouts:{0:'single',1:'wide',2:'grid6'},lettering:{'1:0':{kind:'dialogue',style:'shout',x:.3,y:.2,width:.4,target_x:.8,target_y:.6}}})
assert.deepEqual(comic.comicPages([1,2,3,4,5,6,7,8,9],mixed),[[1],[2,3],[4,5,6,7,8,9]])
assert.equal(mixed.lettering['1:0'].style,'shout')
assert.equal(comic.normalizeComicSettings(mixed).lettering['1:0'].x,.3)
assert.equal(comic.normalizeComicSettings({lettering:{'bad':{x:0},'1:0':{width:999,x:-2}}}).lettering['1:0'].width,.94)
const outline=load('stdComicLettering').balloonOutline(100,100,200,100,'dialogue','speech',420,150)
assert.equal(outline.length,82)
assert.ok(outline[0][0]<300 && outline[80][0]<300)
assert.ok(outline[81][0]>300)
console.log('PASS: mixed layouts, lettering persistence, continuous tail outline')
assert.equal(comic.normalizeComicSettings({panels:{1:{fit:'cover'}}}).panels['1'].motion, undefined)
assert.equal(comic.normalizeComicSettings({panels:{1:{motion:'still'}}}).panels['1'].motion, 'still')
const planned = {project_payload:{structure:{comic_plan:{render_settings:{...mixed,panels:{13:{motion:'pan',fit:'cover'},14:{motion:'still'}}}}}}}
const uploaded = comic.comicSettingsWithUploadedVideo(planned,13)
assert.equal(uploaded.panels['13'].motion,'video')
assert.equal(uploaded.panels['13'].fit,'cover')
assert.equal(uploaded.panels['14'].motion,'still')
assert.deepEqual(uploaded.page_layouts,mixed.page_layouts)
assert.equal(planned.project_payload.structure.comic_plan.render_settings.panels['13'].motion,'pan')
assert.equal(comic.comicSettingsWithUploadedVideo(standard,13).mode,'standard')
assert.equal(comic.selectComicMedia(uploaded.mode,'scene.png','uploaded.mp4'),'uploaded.mp4')
console.log('PASS: manual clip upload overrides planned pan without altering other scenes or layouts')
