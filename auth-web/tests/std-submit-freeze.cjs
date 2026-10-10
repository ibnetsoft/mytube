const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
test('first submission is frozen before asynchronous AE work is accepted',async()=>{
 const events=[];
 const project={id:'p',employee_email:'owner@test',status:'in_progress',submitted_at:null,updated_at:'old',topic_queue_id:null,project_payload:{},progress_payload:{}};
 const scenes=[{scene_number:19}];
 const assets=[{id:'image',asset_type:'image',scene_number:19,status:'assigned',metadata:{gcs_path:'image.png'}},{id:'audio',asset_type:'audio',status:'assigned',metadata:{gcs_path:'audio.mp3'}},{id:'thumb',asset_type:'thumbnail',status:'assigned',metadata:{gcs_path:'thumb.png'}}];
 let submission=null;
 const db={from(table){let patch=null,insert=null;const q={
  select:()=>q,eq:()=>q,is:()=>q,in:()=>q,order:()=>q,limit:()=>q,
  update:value=>{patch=value;return q},insert:value=>{insert=value;return q},
  maybeSingle:async()=>{if(table==='std_projects'&&patch){Object.assign(project,patch);events.push(patch.submitted_at?'freeze':'payload');return {data:project,error:null}};return {data:table==='std_projects'?project:null,error:null}},
  single:async()=>{if(table==='std_project_submissions'&&insert){submission={id:'submission',...insert};events.push('submission');return {data:submission,error:null}};return {data:null,error:null}},
  then(resolve){if(table==='std_project_scenes')resolve({data:scenes,error:null});else if(table==='std_projects'&&patch){Object.assign(project,patch);resolve({data:[project],error:null})}else resolve({data:[],error:null})},
 };return q}};
 const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('app/api/std/projects/[projectId]/submit/route.ts','utf8'),{module:1,target:7}))(ex,name=>{
  if(name==='next/server')return {NextResponse:{json:(body,options)=>({body,status:options?.status||200})}};
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
  if(name.includes('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:assets,error:null})};
  if(name.includes('stdWeb'))return {requireStdUser:async()=>({ok:true,requester:{email:'owner@test',user:{id:'user'}}})};
  if(name.includes('stdPolicy'))return {isStdVideoPromptScene:()=>false};
  if(name.includes('stdThumbnailRender'))return {editableThumbnailError:()=>null};
  if(name.includes('stdLegacySync'))return {syncStdProjectToLegacy:async()=>{}};
  if(name.includes('stdRenderQueue'))return {ensureStdGeneratedSceneAssetsArchived:async(p,s,a)=>a,enqueueStdProjectRender:()=>{throw Error('must wait')}};
  if(name.includes('stdAeMouthQueue'))return {ensureAeMouthJob:async()=>{events.push('ae');assert.ok(project.submitted_at);return {ready:false,job:{id:'mouth',metadata:{fingerprint:'finger'}}}}};
  if(name.includes('stdAeMouth'))return {aeMouthApplicable:()=>true};
  throw Error(name);
 });
 const result=await ex.POST({}, {params:{projectId:'p'}});
 assert.equal(result.status,202,JSON.stringify(result.body));assert.ok(result.body.submitted_at);assert.equal(project.status,'review_requested');
 assert.deepEqual(events.slice(0,3),['payload','freeze','submission']);assert.equal(events[3],'ae');
 assert.equal(submission.metadata.frozen_at,result.body.submitted_at);
});
