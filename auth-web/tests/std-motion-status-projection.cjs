const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
function harness({authorized=true,owned=true,job=null}={}) {
 const calls=[],exports={};
 const db={from(table){const q={select(value){calls.push({table,select:value});return q},eq(){return q},in(){return q},order(){return q},limit(){return q},async maybeSingle(){return {data:table==='std_projects'?(owned?{id:'project'}:null):job,error:null}}};return q}};
 new Function('exports','require',ts.transpileModule(fs.readFileSync('app/api/std/projects/[projectId]/motion-automation/route.ts','utf8'),{compilerOptions:{module:1,target:9}}).outputText)(exports,name=>{
  if(name==='next/server')return {NextResponse:Response};
  if(name.includes('stdWeb'))return {requireStdUser:async()=>authorized?{ok:true,requester:{email:'owner@test'}}:{ok:false,response:Response.json({error:'Unauthorized'},{status:401})}};
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db};throw Error(name);
 });
 return {calls,get:()=>exports.GET(new Request('https://studio.test/api/std/projects/project/motion-automation'),{params:{projectId:'project'}})};
}
test('lightweight status projection preserves engine, progress, supplemental review and final output',async()=>{
 const h=harness({job:{id:'job',kind:'effectcraft_automation',state:'complete',phase:'done',progress:100,results:[{},{}],total_scenes:2,
  supplemental_assets:[{number:1,reviewed:true,file_count:3},{number:2,reviewed:false,file_count:9}],final:{gcs_bucket:'bucket',gcs_path:'final.mp4'}}});
 const res=await h.get(),{job}=await res.json();assert.equal(res.status,200);
 assert.equal(job.engine,'effectcraft');assert.equal(job.reviewed_scenes,2);assert.equal(job.supplemental_scenes,1);assert.equal(job.supplemental_files,3);assert.equal(job.progress,100);assert.match(job.final_url,/final.mp4/);
 const projection=h.calls.find(c=>c.table==='std_project_assets').select;
 assert(!projection.includes('input'));assert(!projection.includes('snapshot'));assert(!projection.split(',').includes('metadata'));
});
test('unauthorized and non-owned projects never query assets',async()=>{
 for(const [options,status] of [[{authorized:false},401],[{owned:false},404]]){const h=harness(options);assert.equal((await h.get()).status,status);assert(!h.calls.some(c=>c.table==='std_project_assets'))}
});
test('missing jobs stay null and in-progress jobs do not expose the final output',async()=>{
 const empty=harness();assert.equal((await (await empty.get()).json()).job,null);
 const h=harness({job:{id:'job',kind:'motion_automation',state:'processing',final:{gcs_bucket:'bucket',gcs_path:'private.mp4'}}});
 const {job}=await (await h.get()).json();assert.equal(job.engine,'ae');assert.equal(job.final_url,null);
});
