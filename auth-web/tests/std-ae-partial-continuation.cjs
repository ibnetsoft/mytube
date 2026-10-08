const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
test('resubmission adds resolved scenes without dropping previously prepared AE directions',async()=>{
 const previous={number:19,speaker_regions:{image_id:'i19'}},next={number:20,speaker_regions:{image_id:'i20'}};
 const job={id:'job',updated_at:'old',metadata:{fingerprint:'stable',state:'direction_pending',input:{scenes:[previous,{number:20,speaker_regions:null}]},results:[{number:19,status:'direction_pending',direction:'review me'},{number:20,status:'needs_review'}]}};
 let change;const filters={};
 const q={update:v=>{change=v;return q},eq:(k,v)=>{filters[k]=v;return q},select:()=>q,maybeSingle:async()=>({data:{...job,...change}})};
 const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdAeMouthQueue.ts','utf8'),{module:1,target:7}))(ex,name=>name==='./supabaseAdmin'?{supabaseAdmin:{from:()=>q,storage:{from:()=>{throw Error('must reuse job')}}}}:{aeMouthInput:()=>({input:{scenes:[previous,next]},fingerprint:'new'}),currentAeMouthJob:()=>job,reviewedAeMouthAssets:()=>{throw Error('not final')}});
 const result=await ex.ensureAeMouthJob({},[],[]);
 assert.equal(result.ready,false);assert.equal(change.metadata.fingerprint,'stable');
 assert.equal(change.metadata.state,'queued');assert.equal(change.metadata.phase,'discovery');
 assert.deepEqual(change.metadata.results,[job.metadata.results[0]]);
 assert.deepEqual(change.metadata.input.scenes,[previous,next]);assert.equal(filters.updated_at,'old');
});
