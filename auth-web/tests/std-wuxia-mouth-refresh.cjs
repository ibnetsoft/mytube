const {test}=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs');
const {mergeWuxiaMouthRefresh}=load('lib/stdWuxiaMouthRefresh.ts');
function fixture(){const manual={id:'manual'},auto={id:'old',automation:'wuxia_mouth_auto/v1'};const p={id:'p',project_payload:{subtitle_source_audio_id:'voice',structure:{wuxia_mouth_policy:{auto_prepare:true},wuxia_ae_package:{scenes:[{scene_id:'S1',graphics:['local-edit'],states:[{asset_id:'ST',sha256:'a',dialogue_mouths:[manual,auto]}]}]}}}};const u={success:true,project_id:'p',audio_id:'voice',states:[{scene_id:'S1',graphics:['local-edit'],asset_id:'ST',sha256:'a',dialogue_mouths:[{id:'new',source_sha256:'a',automation:'wuxia_mouth_auto/v1'}]}]};return {p,u}}
test('refresh preserves manual art and local graphics while replacing automatic mouth only',()=>{const {p,u}=fixture();const n=mergeWuxiaMouthRefresh(p,u);assert.deepEqual(n.project_payload.structure.wuxia_ae_package.scenes[0].states[0].dialogue_mouths.map(m=>m.id),['manual','new']);assert.deepEqual(n.project_payload.structure.wuxia_ae_package.scenes[0].graphics,['local-edit']);assert.equal(p.project_payload.structure.wuxia_ae_package.scenes[0].states[0].dialogue_mouths[1].id,'old')});
test('stale project, voice and original never replace current data',()=>{const {p,u}=fixture();for(const update of [{...u,project_id:'other'},{...u,audio_id:'old'}])assert.equal(mergeWuxiaMouthRefresh(p,update),p);u.states[0].sha256='changed';assert.deepEqual(mergeWuxiaMouthRefresh(p,u),p)});
test('zero selected is valid and clears only auto entries',()=>{const {p,u}=fixture();u.states[0].dialogue_mouths=[];assert.deepEqual(mergeWuxiaMouthRefresh(p,u).project_payload.structure.wuxia_ae_package.scenes[0].states[0].dialogue_mouths,[{id:'manual'}])});

const {preserveWuxiaMouthPreparation}=load('lib/stdWuxiaMouthRefresh.ts');
test('stale saves preserve canonical prepared art and worker mouths; altered originals invalidate them',()=>{const {p}=fixture();const current=p.project_payload.structure;current.wuxia_ae_package.scenes[0].states[0].dialogue_mouth_preparation=[{id:'prepared'}];const next=structuredClone(current);delete next.wuxia_ae_package.scenes[0].states[0].dialogue_mouth_preparation;next.wuxia_ae_package.scenes[0].states[0].dialogue_mouths=[{id:'manual-edited'}];const kept=preserveWuxiaMouthPreparation(current,next);assert.deepEqual(kept.wuxia_ae_package.scenes[0].states[0].dialogue_mouth_preparation,[{id:'prepared'}]);assert.deepEqual(kept.wuxia_ae_package.scenes[0].states[0].dialogue_mouths.map(m=>m.id),['manual-edited','old']);next.wuxia_ae_package.scenes[0].states[0].sha256='new';assert.deepEqual(preserveWuxiaMouthPreparation(current,next).wuxia_ae_package.scenes[0].states[0].dialogue_mouths,[{id:'manual-edited'}])});
test('worker energy survives refresh and stale saves, and is invalidated on source change',()=>{
 const {p,u}=fixture(),sha='a'.repeat(64),state=p.project_payload.structure.wuxia_ae_package.scenes[0].states[0];state.sha256=sha;u.states[0].sha256=sha;
 const loop={automation:'wuxia_energy_auto/v1',contract:'ambient_loop/v1',enabled:true,source_sha256:sha,role:'environment',width:512,height:512,region:[.6,.2,.8,.9],protected_regions:[],start_ms:0,end_ms:3600000,phase_ms:0,repeat:true,frames:[0,1].map(i=>({sha256:String(i).repeat(64),media_url:'/api/std/assets/gcs-file?path='+i,gcs_bucket:'qa',gcs_path:i+'.png',duration_ms:60}))};
 Object.assign(u.states[0],{ambient_loops:[loop],energy_preparation:{source_sha256:sha,decision:'present'},energy_only_motion:true});
 const merged=mergeWuxiaMouthRefresh(p,u).project_payload.structure;assert.equal(merged.wuxia_ae_package.scenes[0].states[0].ambient_loops.length,1);assert.equal(merged.wuxia_ae_package.scenes[0].states[0].energy_only_motion,true);
 const stale=structuredClone(p.project_payload.structure),saved=preserveWuxiaMouthPreparation(merged,stale);assert.equal(saved.wuxia_ae_package.scenes[0].states[0].ambient_loops[0].repeat,true);
 stale.wuxia_ae_package.scenes[0].states[0].sha256='b'.repeat(64);const changed=preserveWuxiaMouthPreparation(merged,stale).wuxia_ae_package.scenes[0].states[0];assert.equal(changed.energy_preparation,undefined);assert.equal(changed.energy_only_motion,undefined);
});
test('energy refresh and stale-save protection work with mouth automation disabled',()=>{
 const {p,u}=fixture(),policy={enabled:false,auto_prepare:false,energy_auto:{enabled:true,auto_prepare:true}};
 p.project_payload.structure.wuxia_mouth_policy=policy;
 u.states[0].energy_preparation={source_sha256:'a',decision:'absent',reason:'Actual artwork reviewed'};
 const merged=mergeWuxiaMouthRefresh(p,u).project_payload.structure;
 assert.equal(merged.wuxia_ae_package.scenes[0].states[0].energy_preparation.decision,'absent');
 const saved=preserveWuxiaMouthPreparation(merged,p.project_payload.structure);
 assert.equal(saved.wuxia_ae_package.scenes[0].states[0].energy_preparation.decision,'absent');
});
test('cinematic-only preparation refreshes before final voice and survives stale saves',()=>{
 const {p,u}=fixture();p.project_payload.structure.wuxia_mouth_policy={enabled:false,auto_prepare:false,cinematic_auto:{enabled:true,auto_prepare:true}};
 u.audio_id='before-voice';u.states[0].cinematic_review={contract:'wuxia_cinematic/v1',source_sha256:'a',passed:true};
 const merged=mergeWuxiaMouthRefresh(p,u).project_payload.structure;
 assert.equal(merged.wuxia_ae_package.scenes[0].states[0].cinematic_review.passed,true);
 const saved=preserveWuxiaMouthPreparation(merged,p.project_payload.structure);
 assert.equal(saved.wuxia_ae_package.scenes[0].states[0].cinematic_review.passed,true);
 const changed=structuredClone(saved);changed.wuxia_ae_package.scenes[0].states[0].sha256='changed';
 assert.equal(preserveWuxiaMouthPreparation(saved,changed).wuxia_ae_package.scenes[0].states[0].cinematic_review,undefined);
});
