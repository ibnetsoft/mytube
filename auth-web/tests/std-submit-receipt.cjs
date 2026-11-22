const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript')
const src=fs.readFileSync('app/api/std/projects/[projectId]/submit/route.ts','utf8')
const start=src.indexOf('export async function GET('),end=src.indexOf('\nfunction hasStoredAssetFile',start)
assert.ok(start>=0&&end>start)
const code=ts.transpileModule(src.slice(start,end).replace('export async function GET','async function GET')+'\nreturn GET',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
function harness({auth=true,owner='owner',submitted='2026-11-22',job={kind:'motion_automation',state:'queued'},error=false}={}){
 const calls=[]
 const db={from(table){const eq=[];return {select(){return this},eq(k,v){eq.push([k,v]);return this},async maybeSingle(){calls.push({table,eq});if(error)return {error:{message:'unavailable'}};if(table==='std_projects')return {data:eq.some(([k,v])=>k==='employee_email'&&v===owner)?{id:'p',submitted_at:submitted,progress_payload:{motion_automation_job_id:'job'}}:null};return {data:job}}}}}
 const requireUser=async()=>auth?{ok:true,requester:{email:'owner'}}:{ok:false,response:{status:401}}
 const next={json:(body,opts)=>({body,status:opts?.status||200})}
 return {calls,GET:new Function('requireStdUser','supabaseAdmin','NextResponse',code)(requireUser,db,next)}
}
test('receipt requires authentication and project ownership',async()=>{let h=harness({auth:false});assert.equal((await h.GET({}, {params:{projectId:'p'}})).status,401);h=harness({owner:'other'});assert.equal((await h.GET({}, {params:{projectId:'p'}})).status,404)})
test('only an active matching project job confirms receipt',async()=>{let h=harness();assert.equal((await h.GET({}, {params:{projectId:'p'}})).body.accepted,true);assert.ok(h.calls[1].eq.some(([k,v])=>k==='project_id'&&v==='p'));for(const job of [null,{kind:'motion_automation',state:'failed'},{kind:'other',state:'queued'}]){h=harness({job});assert.equal((await h.GET({}, {params:{projectId:'p'}})).body.accepted,false)}h=harness({submitted:null});assert.equal((await h.GET({}, {params:{projectId:'p'}})).body.accepted,false);assert.equal(h.calls.length,1)})
test('database errors are never accepted',async()=>{const h=harness({error:true});assert.equal((await h.GET({}, {params:{projectId:'p'}})).status,500)})
