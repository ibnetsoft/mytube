const test = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), ts = require('../node_modules/typescript')
const out = {}
new Function('exports', 'require', ts.transpileModule(fs.readFileSync('lib/stdPolicy.ts', 'utf8'), {compilerOptions:{module:1,target:7}}).outputText)(out, name => {
  if (name === './stdComic') return {isComicProject: () => false}
  if (name === './stdNonverbal') return {isNonverbalProject: () => false}
  if (name === './stdMotionStudio') return {motionForProject: () => null}
  throw new Error(name)
})
test('image-first opt-in keeps all scenes optional without changing legacy projects', () => {
  const imageFirst = {project_payload:{image_first_optional_video:true, required_video_scene_count:0}}
  assert.equal(out.isStdImageFirstProject(imageFirst), true)
  for (const n of [1, 18, 19, 102]) assert.equal(out.isStdRequiredClipScene(n, imageFirst), false)
  assert.equal(out.isStdImageFirstProject({project_payload:{}}), false)
  assert.equal(out.isStdRequiredClipScene(1, {project_payload:{}}), true)
})
