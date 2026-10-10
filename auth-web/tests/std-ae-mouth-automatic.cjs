const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('../node_modules/typescript');
function load(job,db,enqueue,review=()=>{}){
 const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('app/api/worker/ae-mouth/continue/route.ts','utf8'),{module:1,target:7}))(ex,name=>{
  if(name==='crypto')return require(name);
  if(name==='next/server')return {NextResponse:{json:(body,options)=>({body,status:options?.status||200})}};
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
  if(name.includes('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:[],error:null})};
  if(name.includes('stdRenderQueue'))return {enqueueStdProjectRender:enqueue};
  if(name.includes('stdAeMouth'))return {currentAeMouthJob:()=>job,reviewedAeMouthAssets:review};
  throw Error(name);
 });return ex;
}
const request=(token='test-secret',body={projectId:'p',jobId:'j',workerToken:'lease'})=>({headers:new Headers({authorization:'Bearer '+token}),json:async()=>body});
const db={from:table=>{const q={select:()=>q,eq:()=>q,limit:()=>q,update:()=>q,
 single:async()=>({data:{id:'p',status:'submitted',progress_payload:{}}}),
 maybeSingle:async()=>({data:null,error:null}),order:()=>q,
 then(resolve){resolve({data:table==='std_project_scenes'?[]:null,error:null})}};return q;}};
const job=()=>({id:'j',metadata:{automatic:true,state:'processing',phase:'auto_enqueue',worker_token:'lease'}});
test('internal continuation rejects unauthorized and malformed requests before reading data',async()=>{
 process.env.SUPABASE_SERVICE_ROLE_KEY='test-secret';
 const route=load(null,{from:()=>{throw Error('must not read')}},()=>{throw Error('must not enqueue')});
 assert.equal((await route.POST(request('wrong'))).status,401);
 assert.equal((await route.POST(request('test-secret',{projectId:'p'}))).status,400);
});
test('continuation requires current job, live lease, automatic enqueue phase and full result validation',async()=>{
 process.env.SUPABASE_SERVICE_ROLE_KEY='test-secret';
 for(const patch of [{state:'reviewed'},{phase:'auto_review'},{worker_token:'other'},{automatic:false}]){
  const j=job();Object.assign(j.metadata,patch);
  assert.equal((await load(j,db,()=>assert.fail('must not enqueue')).POST(request())).status,409);
 }
 const route=load(job(),db,()=>assert.fail('must not enqueue'),()=>{throw Error('unreviewed scene')});
 assert.equal((await route.POST(request())).status,409);
});
test('lost response retry uses the same render primary key even after prior render finishes',async()=>{
 process.env.SUPABASE_SERVICE_ROLE_KEY='test-secret';let ids=[];
 const route=load(job(),db,async(p,options)=>{ids.push(options.taskId);assert.equal(options.jobId,'j');return{id:options.taskId,status:ids.length===1?'pending':'completed'};});
 const first=await route.POST(request()),second=await route.POST(request());
 assert.equal(first.status,200);assert.equal(second.status,200);
 assert.equal(first.body.render_queue_id,second.body.render_queue_id);
 assert.match(ids[0],/^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-a[0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('queue registrar returns the saved completed receipt without building or inserting again',async()=>{
 const receipt={id:'fixed',status:'completed',metadata:{ae_mouth_job_id:'j',std_web_project_id:'p'}};
 const tables=[];
 const db={from:table=>{tables.push(table);const q={select:()=>q,eq:()=>q,
  maybeSingle:async()=>({data:table==='std_projects'?{id:'p',topic_queue_id:3373}:receipt}),
  order:async()=>({data:[]})};return q;}};
 const ex={};new Function('exports','require',ts.transpile(fs.readFileSync('lib/stdRenderQueue.ts','utf8'),{module:1,target:7}))(ex,name=>{
  if(name==='crypto')return require(name);
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};
  if(name.includes('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:[],error:null})};
  return {};
 });
 assert.deepEqual(await ex.enqueueStdProjectRender('p',{jobId:'j',taskId:'fixed'}),receipt);
 assert.deepEqual(tables,['std_projects','std_project_scenes','remote_render_queue']);
 await assert.rejects(()=>ex.enqueueStdProjectRender('p',{jobId:'different',taskId:'fixed'}),/does not match/);
});
