const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
function fixture(existing){
 let change,inserted;const input={scenes:[{number:5,original_video:{id:'video'}},{number:19,speaker_regions:{image_id:'i'}}]};
 const q={update:v=>{change=v;return q},insert:v=>{inserted=v;return q},eq:()=>q,select:()=>q,maybeSingle:async()=>({data:{...existing,...change}}),single:async()=>({data:inserted})};
 const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdAeMouthQueue.ts','utf8'),{module:1,target:7}))(ex,n=>n==='./supabaseAdmin'?{supabaseAdmin:{from:()=>q,storage:{from:()=>({upload:async()=>({}),remove:async()=>({})})}}}:{aeMouthInput:()=>({input,fingerprint:'fp'}),currentAeMouthJob:()=>existing,reviewedAeMouthAssets:()=>{}});
 return {run:retry=>ex.ensureAeMouthJob({id:'p'},[],[],retry),get change(){return change},get inserted(){return inserted}};
}
test('submission queues video geometry without running analysis in HTTP request',async()=>{
 const f=fixture(null);assert.equal((await f.run()).ready,false);assert.equal(f.inserted.metadata.auto_video_coordinates,true);
 assert.equal(f.inserted.metadata.state,'queued');assert.equal(f.inserted.metadata.input.scenes[0].original_video.id,'video');
});
test('resubmission resumes previously skipped videos and preserves prepared image work',async()=>{
 const good={number:19,status:'direction_pending'},job={id:'j',metadata:{state:'direction_pending',input:{scenes:[]},results:[{number:5,status:'skipped',skip_reason:'missing_speaker_coordinates'},good]}};
 const f=fixture(job);await f.run();assert.equal(f.change.metadata.auto_video_coordinates,true);assert.deepEqual(f.change.metadata.results,[good]);
});
test('active worker and already accepted final render are not overwritten',async()=>{
 for(const extra of [{state:'processing'},{state:'reviewed',auto_render_queue_id:'render'}]){
 const f=fixture({id:'j',metadata:{...extra,results:[{number:5,status:'skipped',skip_reason:'missing_speaker_coordinates'}]}});
 await f.run();assert.equal(f.change,undefined);
 }
});
test('unchanged uncertain automatic result waits for user action instead of repeated analysis',async()=>{
 const f=fixture({id:'j',metadata:{state:'direction_pending',auto_video_coordinates:true,results:[{number:5,status:'needs_review'}]}});
 await f.run();assert.equal(f.change,undefined);
});
