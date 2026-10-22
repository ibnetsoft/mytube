const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
function fixture(options={}){
 const calls=[],exports={};
 const rows={std_projects:{id:'project',pipeline_run_id:'old-run'},std_pipeline_runs:null,std_pipeline_stages:[],remote_render_queue:null,...options.rows};
 const db={from(table){calls.push(table);const q={select(value){assert(!value.includes('manifest'));assert(!value.includes('id,progress_payload'));return q},eq(){return q},async maybeSingle(){return {data:rows[table],error:options.errorTable===table?{message:'DB unavailable'}:null}},then(resolve,reject){return q.maybeSingle().then(resolve,reject)}};return q}};
 new Function('exports','require',ts.transpileModule(fs.readFileSync('app/api/std/projects/[projectId]/pipeline/route.ts','utf8'),{compilerOptions:{module:1,target:9}}).outputText)(exports,id=>{
  if(id==='next/server')return {NextResponse:Response};
  if(id.includes('supabaseAdmin'))return {supabaseAdmin:db};
  if(id.includes('stdWeb'))return {requireStdUser:async()=>options.unauthorized?{ok:false,response:Response.json({error:'Unauthorized'},{status:401})}:{ok:true,requester:{email:'owner@test'}}};throw Error(id);
 });
 return {calls,get:()=>exports.GET(new Request('https://studio.test/api/std/projects/project/pipeline'),{params:{projectId:'project'}})};
}
test('stale pipeline reference returns a visible missing-record state without reading stages',async()=>{
 const f=fixture(),response=await f.get(),data=await response.json();assert.equal(response.status,200);assert.equal(data.run,null);assert.equal(data.status,'missing_run');assert(data.warning);assert.deepEqual(f.calls,['std_projects','std_pipeline_runs']);
});
test('no submission is not an error, and unrelated or unauthorized projects cannot read runs',async()=>{
 for(const [options,status]of [[{rows:{std_projects:{id:'project'}}},200],[{rows:{std_projects:null}},404],[{unauthorized:true},401]]){const f=fixture(options);assert.equal((await f.get()).status,status);assert(!f.calls.includes('std_pipeline_runs'))}
});
test('real DB failures are not disguised as absent records',async()=>{
 for(const table of ['std_pipeline_runs','std_pipeline_stages','remote_render_queue']){
  const f=fixture({rows:{std_pipeline_runs:{id:'run',status:'processing',render_queue_id:'render'}},errorTable:table});assert.equal((await f.get()).status,table==='std_pipeline_stages'?500:503);
 }
});
test('existing runs retain stages and optional render status',async()=>{
 const f=fixture({rows:{std_pipeline_runs:{id:'run',status:'processing',render_queue_id:'render'},std_pipeline_stages:[{stage:'render',state:'queued'}],remote_render_queue:{status:'pending',progress:0}}});
 const res=await f.get(),data=await res.json();assert.equal(res.status,200);assert.equal(data.run.id,'run');assert.equal(data.stages.length,1);assert.equal(data.render.status,'pending');
});
