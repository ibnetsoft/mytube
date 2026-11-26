const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript'),e={}
new Function('exports',ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../lib/stdScriptSceneFields.ts'),'utf8'),{compilerOptions:{module:1,target:7}}).outputText)(e)
test('script editor reads the canonical database speech and image fields',()=>{
 const s={scene_text:'뭐야…… 이건.',image_prompt:'emerald spirit crystal',narration_text:undefined,visual_prompt:undefined};assert.equal(e.scriptSceneSpeech(s),'뭐야…… 이건.');assert.equal(e.scriptSceneVisual(s),'emerald spirit crystal')
})
test('silent cuts stay empty and visual instructions never become TTS text',()=>{
 assert.equal(e.scriptSceneSpeech({scene_text:'',narration_text:'stale text',image_prompt:'not speech'}),'');assert.equal(e.scriptSceneSpeech({image_prompt:'not speech'}),'')
})
test('legacy aliases remain readable when canonical fields are absent',()=>{
 assert.equal(e.scriptSceneSpeech({narration_text:'legacy speech'}),'legacy speech');assert.equal(e.scriptSceneVisual({visual_prompt:'legacy art'}),'legacy art')
})
