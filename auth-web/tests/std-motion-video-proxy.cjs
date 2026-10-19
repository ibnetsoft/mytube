const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),crypto=require('crypto')
function fixture(mode='hybrid',ambiguous=false) {
 const snapshot=JSON.stringify({project:{employee_email:'owner@test'},motion:{automation:{mode,max_ai_clips:1,max_ai_seconds:5}},model_ref:{id:'chosen',fingerprint:'config-hash'},scenes:[{end:30}]})
 const state={creates:0,polls:0,models:0},job={id:'job',updated_at:'version1',metadata:{kind:'motion_automation',state:'processing',worker_token:'lease',
  input:{snapshot_json:snapshot,fingerprint:crypto.createHash('sha256').update(snapshot).digest('hex')},plans:[{number:1,ai:{start:0,duration:4,prompt:'Original identity; slight wind'}}],ai_sources:{'1':{bucket:'source',path:'std-motion/job/sources/actual.png'}}}}
 const db={from(){let update;const q={select(){return q},eq(){return q},update(value){update=value;return q},async maybeSingle(){if(update)Object.assign(job,update);return {data:job,error:null}}};return q},async rpc(_,args){Object.assign(job.metadata,args.p_patch);return {data:job.metadata,error:null}}}
 const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync('app/api/worker/motion-video/route.ts','utf8'),{compilerOptions:{module:1,target:9}}).outputText)(ex,name=>{
  if(name==='crypto')return crypto
  if(name==='next/server')return {NextResponse:{json:(body,options={})=>({body,status:options.status||200})}}
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db}
  if(name.includes('stdVideoModelStore'))return {selectedVideoModel:async()=>{state.models++;return {config:{id:'chosen'},secret:'never-return-this',fingerprint:'config-hash'}}}
  if(name.includes('gcsStorage'))return {createGcsSignedReadUrl:async()=>'https://storage.test/signed'}
  if(name.includes('stdMotionVideoProvider'))return {createProviderVideo:async()=>{state.creates++;if(ambiguous)throw Error('network disconnected');return {id:'request1',status_url:'https://queue.fal.run/request1/status'}},pollProviderVideo:async()=>{state.polls++;return {state:'complete',url:'https://v.fal.media/output.mp4'}}}
  throw Error(name)
 })
 const request=(token='lease')=>ex.POST({headers:new Headers({authorization:'Bearer fixture-service-role'}),json:async()=>({job_id:'job',worker_token:token,scene_number:1,action:'create'})})
 return {state,job,request}
}
test('proxy enforces lease and AE-only mode before loading model credentials',async()=>{
 const old=process.env.SUPABASE_SERVICE_ROLE_KEY;process.env.SUPABASE_SERVICE_ROLE_KEY='fixture-service-role'
 try{const f=fixture('ae_only');assert.equal((await f.request()).status,409);assert.equal(f.state.models,0);assert.equal((await f.request('other')).status,409);assert.equal(f.state.creates,0)}finally{if(old===undefined)delete process.env.SUPABASE_SERVICE_ROLE_KEY;else process.env.SUPABASE_SERVICE_ROLE_KEY=old}
})
test('paid creation is checkpointed once; repeated calls poll the same request',async()=>{
 const old=process.env.SUPABASE_SERVICE_ROLE_KEY;process.env.SUPABASE_SERVICE_ROLE_KEY='fixture-service-role'
 try{const f=fixture();assert.equal((await f.request()).body.state,'pending');assert.equal(f.job.metadata.provider_requests['1'].id,'request1');const r=await f.request();assert.equal(r.body.state,'complete');assert.equal(f.state.creates,1);assert.equal(f.state.polls,1);assert.ok(!JSON.stringify(r).includes('never-return-this'))
 f.job.metadata.plans[0].ai.prompt='Changed direction';assert.equal((await f.request()).status,409);assert.equal(f.state.creates,1)
 }finally{if(old===undefined)delete process.env.SUPABASE_SERVICE_ROLE_KEY;else process.env.SUPABASE_SERVICE_ROLE_KEY=old}
})
test('ambiguous paid POST never automatically submits a duplicate',async()=>{
 const old=process.env.SUPABASE_SERVICE_ROLE_KEY;process.env.SUPABASE_SERVICE_ROLE_KEY='fixture-service-role'
 try{const f=fixture('hybrid',true);assert.equal((await f.request()).status,409);assert.equal(f.job.metadata.provider_requests['1'].state,'needs_reconcile');assert.equal((await f.request()).status,409);assert.equal(f.state.creates,1)}finally{if(old===undefined)delete process.env.SUPABASE_SERVICE_ROLE_KEY;else process.env.SUPABASE_SERVICE_ROLE_KEY=old}
})
