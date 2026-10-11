const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const cp = require('node:child_process')
const compile = source => ts.transpile(source, {module:1,target:7})
const nv = {}
new Function('exports',compile(fs.readFileSync('lib/stdNonverbal.ts','utf8')))(nv)
const p = JSON.parse(cp.execFileSync('../.venv-script/bin/python',['-c',`import sys,json,importlib.util
sys.path.insert(0,'..')
s=importlib.util.spec_from_file_location('fixture','../tests/test_nonverbal_preschool.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
print(json.dumps(m.build_package(m.fixture(),{'target_duration_seconds':60})))`],{encoding:'utf8'}))
const project = {id:'nv',project_payload:p,progress_payload:{audio_duration:999,subtitles:[{text:'stale speech'}]}}
assert.equal(nv.hasReadyNonverbalPlan(project),true)
const malformed = structuredClone(project);malformed.project_payload.structure.scenes[0].narration='hello'
assert.equal(nv.hasReadyNonverbalPlan(malformed),false)
const prepared = {};new Function('exports','require',compile(fs.readFileSync('lib/preparedTopic.ts','utf8')))(prepared,name=>name.includes('stdNonverbal')?nv:{})
assert.equal(prepared.isPreparedUserTopic({status:'pending',generated_title:p.generated_title,category_id:1,publish_metadata:p.publish_metadata,pregenerated_structure_status:'ready',pregenerated_script_status:'ready',pregenerated_script:'',pregenerated_structure:p.structure}),true)
const policy={};new Function('exports','require',compile(fs.readFileSync('lib/stdPolicy.ts','utf8')))(policy,name=>name.includes('stdNonverbal')?nv:{isComicProject:()=>false})
assert.equal(policy.stdRequiredVideoSceneCount(project),0)
const mouth={};new Function('exports','require',compile(fs.readFileSync('lib/stdAeMouth.ts','utf8')))(mouth,name=>name.includes('stdNonverbal')?nv:{})
assert.equal(mouth.aeMouthApplicable(project,[{scene_number:19}]),false)
let stored
const queue={};new Function('exports','require',compile(fs.readFileSync('lib/stdRenderQueue.ts','utf8')+'\nexport {nonverbalTiming,renderAudioAsset};'))(queue,name=>{
 if(name.includes('stdNonverbal'))return nv
 if(name.includes('gcsStorage'))return {gcsBucketName:()=> 'test',uploadGcsBuffer:async x=>{stored=x}}
 return {}
})
const scenes=p.structure.scenes.map(s=>({scene_number:s.scene_number}))
assert.deepEqual(queue.nonverbalTiming(project,scenes),{duration:60,starts:[0,6,12,18,24,30,36,42,48,54]})
assert.throws(()=>queue.nonverbalTiming(project,scenes.slice(1)))
;(async()=>{
 const audio=await queue.renderAudioAsset(project,scenes,[{asset_type:'audio',file_name:'stale-narration.mp3'}])
 assert.equal(audio.file_name,'nonverbal-silence.wav')
 assert.equal(stored.data.readUInt32LE(40),60*16000*2)
 assert.equal(stored.data.subarray(44).some(b=>b!==0),false)
 assert.equal(audio.metadata.duration_seconds,60)
 console.log('PASS: validated silent topic readiness, no AI clips, exact scene clock, silent WAV instead of stale narration')
})().catch(e=>{console.error(e);process.exitCode=1})
