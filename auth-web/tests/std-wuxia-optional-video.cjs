const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs'),p=load('lib/stdPolicy.ts')
test('selected wuxia video prompts survive without forcing opening footage',()=>{
 const topic={required_video_scene_count:0,pregenerated_structure:{required_video_scene_count:0,wuxia_video_prompt_scenes:[10,28,57]}}
 assert.equal(p.stdRequiredVideoSceneCount(topic),0)
 for(const n of [10,28,57]){assert(p.isStdVideoPromptScene(n,topic));assert(!p.isStdRequiredClipScene(n,topic))}
 for(const n of [1,9,11,58])assert(!p.isStdVideoPromptScene(n,topic))
 assert(p.isStdVideoPromptScene(28,{project_payload:{structure:topic.pregenerated_structure,required_video_scene_count:0}}))
})

const visual=load('lib/stdVisualStepStatus.ts')
test('optional video scope is not labelled no-video and does not require uploads',()=>{
 const base={required_video_scene_count:0,pregenerated_structure:{scenes:[{scene_number:14,image_url:'still.png'}]}}
 const optional={...base,pregenerated_structure:{...base.pregenerated_structure,wuxia_video_prompt_scenes:[14]}}
 assert.equal(visual.savedStdVisualStepStatus(optional).videoNotRequired,false)
 assert.equal(visual.savedStdVisualStepStatus(optional).isVideoStepDone,true)
 assert.equal(visual.savedStdVisualStepStatus(base).videoNotRequired,true)
 assert.equal(visual.savedStdVisualStepStatus({...base,project_payload:{wuxia_state_clips:{state:{media_url:'clip.mp4'}}}}).videoNotRequired,false)
})
