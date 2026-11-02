const test = require('node:test'), assert = require('node:assert/strict')
const { stripPostworkDirection } = require('./load-ts-module.cjs')('lib/stdUserWebPayload.ts')
test('removes nested postwork plans without modifying the source or editor content', () => {
 const original = {script:'narration', structure:{scene_direction_plans:[{secret:'direction'}], scenes:[{scene_number:1, scene_text:'line', image_url:'image', ae_motion_plan:{keys:[1]}, scene_direction_plan:{action:'move'}, image_generation_policy:{cost:1}}]}}
 const filtered = stripPostworkDirection(original)
 assert.deepEqual(filtered, {script:'narration', structure:{scenes:[{scene_number:1,scene_text:'line',image_url:'image'}]}})
 assert.equal(original.structure.scenes[0].ae_motion_plan.keys[0],1)
})
