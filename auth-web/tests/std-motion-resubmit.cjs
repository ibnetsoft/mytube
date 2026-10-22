const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('../node_modules/typescript');
function route(register){
 const out={},project={id:'p',project_payload:{render_settings:{motion:{enabled:true}}}},calls=[];
 const query={select(){return this},eq(){return this},maybeSingle:async()=>({data:project}),order:async()=>({data:[{scene_number:1}]})};
 const imports={
  '@/lib/stdMotionAutomation':{motionAutomationEnabled:()=>true,registerMotionAutomation:async(...args)=>{calls.push(args);return register(...args)}},
  '@/lib/stdProjectAssets':{loadStdProjectAssets:async()=>({data:[{id:'audio'}]})},
  '@/lib/stdAeMouth':{aeMouthApplicable:()=>{throw Error('legacy mouth path used')}},
  '@/lib/stdAeMouthQueue':{ensureAeMouthJob:()=>{throw Error('legacy job created')}},
  'next/server':{NextResponse:{json:(body,options)=>({body,status:options?.status||200})}},
  '@/lib/supabaseAdmin':{supabaseAdmin:{from:()=>query}},
  '@/lib/stdRenderQueue':{getStdProjectRenderHistory:async()=>[],enqueueStdProjectRender:()=>{throw Error('unreviewed final render enqueued')}},
  '@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:'u',user:{id:'owner'}}})},
  '@/lib/stdAeScenePreparation':{hasAeSceneIntent:()=>false}
 };
 const code=ts.transpileModule(fs.readFileSync('app/api/std/projects/[projectId]/reopen/route.ts','utf8'),{compilerOptions:{module:1,target:9}}).outputText;
 new Function('exports','require',code)(out,id=>{if(!(id in imports))throw Error(id);return imports[id]});
 return {run:()=>out.POST({}, {params:{projectId:'p'}}),calls};
}
test('EC re-submit freezes a new renderer job instead of entering legacy mouth/final-render paths',async()=>{
 const r=route(async()=>({job_id:'ec-job',run_id:'run'})),result=await r.run();
 assert.equal(result.status,202);assert.equal(result.body.motion_automation,true);assert.equal(result.body.job_id,'ec-job');
 assert.equal(r.calls.length,1);assert.equal(r.calls[0][3],'owner');assert.equal(r.calls[0][4],true);
 assert.equal(r.calls[0][2][0].id,'audio');
});
test('registration failure is surfaced without falling through to another renderer',async()=>{
 const r=route(async()=>{throw Error('Project changed; save and submit again')}),result=await r.run();
 assert.equal(result.status,409);assert.match(result.body.error,/Project changed/);assert.equal(r.calls.length,1);
});
