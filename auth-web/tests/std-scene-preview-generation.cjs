const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
function load(file,deps={}){const out={};new Function('require','exports',ts.transpile(fs.readFileSync(file,'utf8'),{module:1,target:7}))((id)=>deps[id]||require(id),out);return out}
const preview=load('auth-web/lib/stdPreviewAudio.ts',{'./stdSubtitleFragments':{isSubtitleClosingPunctuation:()=>false}});
(async()=>{let generations=0,reads=0,pauses=0; const missing=()=>Object.assign(new Error('missing'),{code:'audio_not_cached'});
assert.equal(await preview.prepareScenePreviewClip(async()=> 'saved',async()=>{generations++;return 'new'},async()=>{}),'saved');assert.equal(generations,0);
assert.equal(await preview.prepareScenePreviewClip(async()=>{throw missing()},async()=>{generations++;return 'new'},async()=>{}),'new');assert.equal(generations,1);
assert.equal(await preview.prepareScenePreviewClip(async()=>{if(++reads<3)throw missing();return 'existing'},async()=>{generations++;throw Object.assign(new Error('claimed'),{code:'audio_generation_claimed',status:409})},async()=>{pauses++}),'existing');assert.equal(generations,2);assert.equal(pauses,2);
const page=fs.readFileSync('auth-web/app/std/page.tsx','utf8');assert.match(page,/selectedScene != null \? subtitle\?\.scene_number === selectedScene : index === startIndex/);assert.doesNotMatch(preview.savedAudioRequiredMessage('ko'),/저장\+TTS/);console.log('PASS: preview reuses existing audio, generates only requested missing scene, and waits for concurrent generation')})().catch(e=>{console.error(e);process.exitCode=1});
