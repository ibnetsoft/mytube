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
    assert.equal(motion.sceneMotionStyle('zoom_in', 30, 10, 20).transform, 'translate(0%, 0%) scale(1.06)')
    assert.equal(motion.sceneMotionStyle('zoom_out', 10, 10, 20).transform, 'translate(0%, 0%) scale(1.06)')
    assert.equal(motion.sceneMotionStyle('pan_left', 20, 10, 20).transform, 'translate(-6%, 0%) scale(1.12)')
    assert.equal(motion.sceneMotionStyle('none', 15, 10, 20).transform, 'translate(0%, 0%) scale(1)')

    assert.equal(motion.sceneMotionSpeed({}), 1.5)
    assert.equal(motion.sceneMotionSpeed({image_effect: 'pan_left'}), 1)
    assert.equal(motion.sceneMotionSpeed({metadata: {motion_speed: '3'}}), 3)
    assert.equal(motion.sceneMotionSpeed({metadata: {motion_speed: 99}}), 3)
    assert.equal(motion.sceneMotionStyle('zoom_in', 20, 10, 20, 3).transform, 'translate(0%, 0%) scale(1.12)')
    const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
    const start = page.indexOf('    const applySelectedSceneTransition =')
    const end = page.indexOf('    const setSubtitleBlockVoice', start)
    const source = compile(page.slice(start, end) + '\nreturn applySelectedSceneTransition;')
    const original = {project: {id: 'p', project_payload: {}}, scenes: [{scene_number: 1, metadata: {transition_effect: 'dissolve'}}, {scene_number: 13}]}
    let saved, state = original, failed = false
    const apply = new Function('selectedProject', 'selectedSubtitleSceneNumbers', 'sceneEffectSavingRef', 'setIsSceneEffectSaving', 'setIsTransitionPickerOpen', 'setMessage', 'setSelectedProject', 'rememberProjectState', 'fetch', 'authedJsonHeaders', 'setIsMotionPickerOpen', source)(
        original, [1], {current: false}, () => {}, () => {}, () => {}, fn => {state = fn(state)}, () => {},
        async (_, options) => {saved = JSON.parse(options.body); return {ok: !failed, text: async () => 'save failed'}}, {}, () => {},
    )
    await apply('zoom_out', 'image_effect', [1, 13])
    assert.equal(saved.project_payload.scenes[0].metadata.image_effect, undefined)
    assert.equal(saved.project_payload.structure.scenes[0].metadata.transition_effect, 'dissolve')
    assert.equal(saved.project_payload.scenes[1].metadata.image_effect, 'zoom_out')
    assert.equal(motion.sceneMotion(state.scenes[1]), 'zoom_out')
    const previousSave = saved
    await apply('none', 'image_effect', Array.from({length: 12}, (_, i) => i + 1))
    assert.equal(saved, previousSave, 'Hook-only selection must not save image motion')
    await apply('fade', 'transition_effect', [1, 13])
    assert.equal(saved.project_payload.scenes[0].metadata.transition_effect, 'fade')
    await apply('zoom_out', 'image_effect', [13])
    await apply('2', 'motion_speed', [1, 13])
    assert.equal(saved.project_payload.scenes[0].metadata.motion_speed, undefined)
    assert.equal(saved.project_payload.scenes[1].metadata.motion_speed, '2')
    assert.equal(motion.sceneMotionSpeed(state.scenes[1]), 2)
    failed = true
    await apply('none', 'image_effect', [13])
    assert.equal(motion.sceneMotion(state.scenes[1]), 'zoom_out', 'failed save must not replace committed motion')
    console.log('PASS: scene motion endpoints, clamping, metadata persistence, targeted updates and failed saves')
}
main().catch(error => {console.error(error); process.exitCode = 1})
