const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdRenderQueue.ts','utf8'),{module:1,target:7}))(ex,name=>{
 if(name==='crypto')return require(name);
 if(name.includes('supabaseAdmin'))return {supabaseAdmin:{}};
 return {};
});
const project=(asset,layer,plan={enabled:true,preset:'parallax'})=>({project_payload:{structure:{scenes:[{
 scene_number:19,ae_motion_plan:plan,metadata:{ae_motion_asset:asset,...(layer?{psd_layer_asset:layer}:{})}
}]}}});
test('reviewed GCS scene postprocess replaces the original visual',()=>{
 const asset={status:'ready',storage_provider:'gcs',gcs_bucket:'bucket',gcs_path:'air/scene-19.mp4',file_size:123};
 const result=ex.reviewedScenePostprocessAsset(project(asset),19);
 assert.equal(result.asset_type,'video');assert.equal(result.metadata.gcs_path,'air/scene-19.mp4');
});
test('pending postprocess delays final render while terminal failure falls back to original',()=>{
 assert.throws(()=>ex.reviewedScenePostprocessAsset(project({status:'rendering'}),19),error=>error.code==='SCENE_POSTPROCESS_PENDING');
 assert.equal(ex.reviewedScenePostprocessAsset(project({status:'needs_attention'}),19),null);
});
test('layer template is consumed only after its PSD package is approved',()=>{
 const asset={status:'ready',storage_provider:'gcs',gcs_path:'air/scene-19.mp4'};
 const plan={enabled:true,template:'manga',preset:'parallax'};
 const p=project(asset,{qa_status:'needs_review'},plan);p.project_payload.structure.scenes[0].metadata.ae_effect_asset=asset;p.project_payload.structure.scenes[0].ae_effect_plan=plan;delete p.project_payload.structure.scenes[0].ae_motion_plan;
 assert.equal(ex.reviewedScenePostprocessAsset(p,19),null);
 p.project_payload.structure.scenes[0].metadata.psd_layer_asset.qa_status='approved';
 assert.equal(ex.reviewedScenePostprocessAsset(p,19).metadata.gcs_path,'air/scene-19.mp4');
});
