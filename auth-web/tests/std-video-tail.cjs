const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('../node_modules/typescript');
const lib={};new Function('exports',ts.transpile(fs.readFileSync('lib/stdVideoTail.ts','utf8'),{module:1,target:7}))(lib);
const scene={scene_number:14,metadata:{duration_seconds:5}};
const original={asset_type:'video',metadata:{gcs_path:'source.mp4',duration_seconds:5}};
const payload={subtitles:[{scene_number:14,start_num:10,end_num:18}],structure:{scenes:[{scene_number:14,metadata:{}}]}};
test('short source cannot bypass AE processing and review',()=>{
 assert.throws(()=>lib.reviewedVideoTail(scene,original,payload),/14번 씬/);
});
test('reviewed matching AE output replaces original in render manifest',()=>{
 const tail={status:'ready',duration_seconds:8,video_tail_policy:lib.VIDEO_TAIL_POLICY,render_sha256:'a'.repeat(64),visual_review:{decision:'approved',reviewer:'Codex',note:'Actual frames checked',render_sha256:'a'.repeat(64)},source_image:{object_path:'source.mp4'},gcs_bucket:'bucket',gcs_path:'reviewed-tail.mp4'};
 const p=structuredClone(payload);p.structure.scenes[0].metadata.ae_motion_asset=tail;
 assert.equal(lib.reviewedVideoTail(scene,original,p).metadata.gcs_path,'reviewed-tail.mp4');
 tail.visual_review.render_sha256='b'.repeat(64);
 assert.throws(()=>lib.reviewedVideoTail(scene,original,p),/검수/);
});
test('long enough original needs no frozen tail',()=>{
 assert.equal(lib.reviewedVideoTail(scene,{...original,metadata:{duration_seconds:9}},payload).metadata.duration_seconds,9);
});
