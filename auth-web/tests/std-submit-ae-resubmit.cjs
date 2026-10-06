const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
function fixture({ready=false,applicable=true,closed=false,queueError=''}={}) {
 const calls=[];
 const project={id:'p',employee_email:'owner@test',status:closed?'approved':'review_requested',submitted_at:'2026-10-04',updated_at:'old',topic_queue_id:3373,project_payload:{},progress_payload:{}};
 const assets=[{asset_type:'image',scene_number:19,metadata:{gcs_path:'image.png'}},{asset_type:'audio',metadata:{gcs_path:'audio.mp3'}},{asset_type:'thumbnail',metadata:{gcs_path:'thumbnail.png'}}];
 const db={from(table){calls.push(table);let updating=false;const q={select:()=>q,eq:()=>q,in:()=>q,update:()=>{updating=true;return q;},maybeSingle:async()=>({data:updating?{id:'p'}:project}),then(resolve){resolve({data:table==='std_project_scenes'?[{scene_number:19}]:assets});}};return q;}};
 const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('app/api/std/projects/[projectId]/submit/route.ts','utf8'),{module:1,target:7}))(ex,name=>{
  if(name==='next/server')return {NextResponse:{json:(body,options)=>({body,status:options?.status||200})}};
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
  if(name.includes('stdWeb'))return {requireStdUser:async()=>({ok:true,requester:{email:'owner@test'}})};
  if(name.includes('stdPolicy'))return {isStdVideoPromptScene:()=>false};
  if(name.includes('stdThumbnailRender'))return {editableThumbnailError:()=>null};
  if(name.includes('stdLegacySync'))return {};
  if(name.includes('stdRenderQueue'))return {ensureStdGeneratedSceneAssetsArchived:async(p,s,a)=>a,enqueueStdProjectRender:()=>{throw Error('must not enqueue final render')}};
  if(name.includes('stdAeMouthQueue'))return {ensureAeMouthJob:async()=>{calls.push('ensure-ae');if(queueError)throw Error(queueError);return {ready};}};
  if(name.includes('stdAeMouth'))return {aeMouthApplicable:()=>applicable};
  throw Error(name);
 });return {run:()=>ex.POST({}, {params:{projectId:'p'}}),calls,project};
}
test('previously submitted project queues AE for current assets before duplicate guard',async()=>{
 const f=fixture(),r=await f.run();assert.equal(r.status,202);assert.equal(r.body.postprocess_pending,true);assert.ok(f.calls.includes('ensure-ae'));assert.equal(f.project.project_payload.ae_mouth.enabled,true);assert.equal(f.project.submitted_at,'2026-10-04');assert.ok(!f.calls.includes('std_project_submissions'));
});
test('reviewed AE and non-applicable projects retain duplicate final submission protection',async()=>{
 for(const options of [{ready:true},{applicable:false}]){const f=fixture(options),r=await f.run();assert.equal(r.body.already_submitted,true);assert.equal(r.status,200);assert.ok(!f.calls.includes('std_project_submissions'));}
});
test('AE preparation errors are surfaced on resubmission',async()=>{const r=await fixture({queueError:'TTS mismatch'}).run();assert.equal(r.status,409);assert.equal(r.body.error,'TTS mismatch');});
test('closed projects cannot schedule AE',async()=>{const f=fixture({closed:true});assert.equal((await f.run()).status,409);assert.ok(!f.calls.includes('ensure-ae'));});
