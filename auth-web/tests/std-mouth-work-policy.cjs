const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('typescript');
const ex={};new Function('exports',ts.transpileModule(fs.readFileSync('lib/stdMouthWorkPolicy.ts','utf8'),{compilerOptions:{module:1,target:7}}).outputText)(ex);
const scenes=Array.from({length:60},(_,i)=>({scene_number:i+1}));
const project={project_payload:{subtitles:scenes.filter(s=>s.scene_number%2===0).map(s=>({...s,text:'hello',dialogue_kind:'dialogue'}))}};
test('same default ten scene cap as script worker',()=>assert.deepEqual([...ex.mouthWorkScenes(project,scenes)],[20,22,24,26,28,30,32,34,36,38]));
test('frozen scope survives subtitle changes including disabled scope',()=>{
 for(const list of [[],[22,24]]) assert.deepEqual([...ex.mouthWorkScenes(project,scenes,[{metadata:{kind:'mouth_work_selection',scene_numbers:list}}])],list);
});
test('custom zero and disabled policy',()=>{for(const p of [{enabled:false},{max_dialogue_scenes:0}])assert.equal(ex.mouthWorkScenes({project_payload:{...project.project_payload,mouth_work_policy:p}},scenes).size,0)});
