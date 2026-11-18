const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs'),p=load('lib/stdPolicy.ts')
test('selected wuxia video prompts survive without forcing opening footage',()=>{
 const topic={required_video_scene_count:0,pregenerated_structure:{required_video_scene_count:0,wuxia_video_prompt_scenes:[10,28,57]}}
 assert.equal(p.stdRequiredVideoSceneCount(topic),0)
 for(const n of [10,28,57]){assert(p.isStdVideoPromptScene(n,topic));assert(!p.isStdRequiredClipScene(n,topic))}
 for(const n of [1,9,11,58])assert(!p.isStdVideoPromptScene(n,topic))
 assert(p.isStdVideoPromptScene(28,{project_payload:{structure:topic.pregenerated_structure,required_video_scene_count:0}}))
})
