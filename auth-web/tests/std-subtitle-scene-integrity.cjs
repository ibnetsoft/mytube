const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const exportsObject = {}
new Function('exports', ts.transpileModule(fs.readFileSync(require.resolve('../lib/stdSubtitleSceneIntegrity.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText)(exportsObject)
const { preserveSubtitleScenes } = exportsObject
const scenes = [1, 2, 3, 4].map(scene_number => ({ scene_number, scene_text: `scene ${scene_number}` }))
const previous = scenes.map(scene => ({ id: `saved-${scene.scene_number}`, scene_number: scene.scene_number,
    text: `edited ${scene.scene_number}`, voice_id: 'existing', start_num: scene.scene_number * 5, audio_url: '/recorded.mp3' }))
test('a stale partial save restores omitted scenes with their edited text, audio and timing', () => {
    const result = preserveSubtitleScenes([previous[0], { ...previous[3], text: 'new edit' }], previous, scenes)
    assert.deepEqual(result.recovered, [2, 3])
    assert.deepEqual(result.subtitles[2], previous[2])
    assert.equal(result.subtitles[3].text, 'new edit')
    assert.equal(result.subtitles.length, 4)
})
test('source-only missing scenes are recovered without pretending to have recorded voice or timing', () => {
    const result = preserveSubtitleScenes([previous[0]], [previous[0]], scenes)
    assert.equal(result.subtitles.length, 4)
    assert.equal(result.subtitles[2].restored_audio_pending, true)
    assert.equal(result.subtitles[2].voice_assignment_pending, true)
    assert.equal(result.subtitles[2].audio_url, undefined)
    assert.deepEqual(preserveSubtitleScenes(result.subtitles, result.subtitles, scenes).subtitles, result.subtitles)
})
test('explicit deletion survives refresh and stale incoming rows without erasing source media', () => {
    const result = preserveSubtitleScenes(previous, previous, scenes, [3])
    assert.deepEqual(result.subtitles.map(row => row.scene_number), [1, 2, 4])
    assert.deepEqual(scenes.map(scene => scene.scene_number), [1, 2, 3, 4])
})
test('manual splits and within-scene order survive scene recovery', () => {
    const split = [{ ...previous[1], id: 'a' }, { ...previous[1], id: 'b', text: 'second' }]
    const result = preserveSubtitleScenes(split, previous, scenes)
    assert.deepEqual(result.subtitles.filter(row => row.scene_number === 2), split)
})
