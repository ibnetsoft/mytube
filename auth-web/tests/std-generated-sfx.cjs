const fs=require('fs'),assert=require('node:assert/strict'),ts=require('typescript');require.extensions['.ts']=(m,p)=>m._compile(ts.transpileModule(fs.readFileSync(p,'utf8'),{compilerOptions:{module:1,target:7}}).outputText,p);
const {freezeGeneratedSfx}=require('../lib/stdGeneratedSfx.ts');const cue={id:'hit',cut_id:'C002',prompt:'Stone thud',duration_seconds:1,offset_seconds:.2,volume_db:-18};const project={id:'p',project_payload:{structure:{sfx_generation_plan:{contract:'elevenlabs_sfx_plan/v1',status:'approved',cues:[cue]}}}};const scenes=[{scene_number:7,metadata:{cut_id:'C002'}}],clock=[{number:7,start:9,end:10,source:{id:'source'}}];
assert.equal(freezeGeneratedSfx(project,scenes,clock).cues[0].start,9.2);assert.equal(freezeGeneratedSfx(project,scenes,clock).cues[0].scene_number,7);
assert.throws(()=>freezeGeneratedSfx(project,[{scene_number:2}],clock));
project.project_payload.structure.sfx_generation_plan.status='review';assert.throws(()=>freezeGeneratedSfx(project,scenes,clock));
project.project_payload.structure.sfx_generation_plan.status='approved';cue.offset_seconds=2;assert.throws(()=>freezeGeneratedSfx(project,scenes,clock));
assert.equal(freezeGeneratedSfx({project_payload:{}},[],[]),null);console.log('5 frozen SFX checks passed');
