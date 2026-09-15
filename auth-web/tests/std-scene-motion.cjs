const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
const motion = {}
new Function('exports', compile(fs.readFileSync(path.join(__dirname, '../lib/stdSceneMotion.ts'), 'utf8')))(motion)

async function main() {
    assert.equal(motion.sceneMotion({metadata: {image_effect: 'none'}}), 'none')
    assert.equal(motion.sceneMotion({metadata: {image_effect: 'zoom_out'}, image_effect: 'zoom_in'}), 'zoom_out')
    assert.equal(motion.sceneMotion({}), 'zoom_in')
    assert.equal(motion.sceneMotionStyle('zoom_in', 0, 10, 20).transform, 'translate(0%, 0%) scale(1)')
    assert.equal(motion.sceneMotionStyle('zoom_in', 30, 10, 20).transform, 'translate(0%, 0%) scale(1.15)')
    assert.equal(motion.sceneMotionStyle('zoom_out', 10, 10, 20).transform, 'translate(0%, 0%) scale(1.15)')
    assert.equal(motion.sceneMotionStyle('pan_left', 20, 10, 20).transform, 'translate(-10%, 0%) scale(1.2)')
    assert.equal(motion.sceneMotionStyle('none', 15, 10, 20).transform, 'translate(0%, 0%) scale(1)')

    const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
    const start = page.indexOf('    const applySelectedSceneTransition =')
    const end = page.indexOf('    const setSubtitleBlockVoice', start)
    const source = compile(page.slice(start, end) + '\nreturn applySelectedSceneTransition;')
    const original = {project: {id: 'p', project_payload: {}}, scenes: [{scene_number: 1, metadata: {transition_effect: 'dissolve'}}, {scene_number: 2}]}
    let saved, state = original, failed = false
    const apply = new Function('selectedProject', 'selectedSubtitleSceneNumbers', 'sceneEffectSavingRef', 'setIsSceneEffectSaving', 'setIsTransitionPickerOpen', 'setMessage', 'setSelectedProject', 'rememberProjectState', 'fetch', 'authedJsonHeaders', source)(
        original, [1], {current: false}, () => {}, () => {}, () => {}, fn => {state = fn(state)}, () => {},
        async (_, options) => {saved = JSON.parse(options.body); return {ok: !failed, text: async () => 'save failed'}}, {},
    )
    await apply('zoom_out', 'image_effect', [1])
    assert.equal(saved.project_payload.scenes[0].metadata.image_effect, 'zoom_out')
    assert.equal(saved.project_payload.structure.scenes[0].metadata.transition_effect, 'dissolve')
    assert.equal(saved.project_payload.scenes[1].metadata, undefined)
    assert.equal(motion.sceneMotion(state.scenes[0]), 'zoom_out')
    failed = true
    await apply('none', 'image_effect', [1])
    assert.equal(motion.sceneMotion(state.scenes[0]), 'zoom_out', 'failed save must not replace committed motion')
    console.log('PASS: scene motion endpoints, clamping, metadata persistence, targeted updates and failed saves')
}
main().catch(error => {console.error(error); process.exitCode = 1})
