const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('../node_modules/typescript')
const load=require('./load-ts-module.cjs'),clips=load(path.resolve(__dirname,'../lib/stdWuxiaClips.ts'))
function fixture(){
 const project={id:'p',employee_email:'owner@test',status:'claimed',project_payload:{structure:{wuxia_ae_package:{scenes:[{scene_id:'E01_S01',states:[{asset_id:'s',sha256:'a'.repeat(64)}]}]}}}}
 let stored,updated=[],count=0
 const supabaseAdmin={rpc:async()=>({data:project,error:null}),from:table=>{
  const q={eq:()=>q,maybeSingle:async()=>({data:stored,error:null}),select:()=>q,
   insert:value=>{stored=value;count++;return Promise.resolve({error:null})},
   update:value=>{updated.push({table,value});if(table==='std_project_assets')stored={...stored,...value};return q},
   then:fn=>Promise.resolve({error:null}).then(fn)};return q}}
 const deps={'next/server':{NextResponse:{json:(v,o)=>Response.json(v,o)}},'node:crypto':require('node:crypto'),
  '@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:'owner@test'}})},'@/lib/supabaseAdmin':{supabaseAdmin},
  '@/lib/gcsStorage':{buildStdGcsObjectPath:()=> 'projects/p/clip.mp4',createGcsSignedUploadUrl:async()=>({bucket:'private',signedUrl:'https://storage.test/upload'}),getGcsObjectMetadata:async()=>({size:100,contentType:'video/mp4'})},
  '@/lib/stdContentIdentity':{assetContentIdentity:()=>({script_sha256:'d'.repeat(64)})},'@/lib/stdWuxiaClips':clips}
 const out={},code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../app/api/std/projects/[projectId]/wuxia-clips/route.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
 new Function('exports','require',code)(out,id=>{if(!(id in deps))throw Error(id);return deps[id]})
 const body={state_asset_id:'s',source_state_sha256:'a'.repeat(64),sha256:'b'.repeat(64),file_size:100,mime_type:'video/mp4',width:1280,height:720,duration_seconds:5,source_in_seconds:0,play_seconds:2,start_offset_seconds:0}
 const request=(method,b)=>new Request('https://studio.test/api/std/projects/p/wuxia-clips',{method,body:JSON.stringify(b),headers:{'Content-Type':'application/json'}})
 return {project,body,updated,get stored(){return stored},get count(){return count},post:()=>out.POST(request('POST',body),{params:{projectId:'p'}}),patch:(action)=>out.PATCH(request('PATCH',{asset_id:stored.id,action}),{params:{projectId:'p'}})}
}
test('upload completes only its source-bound auxiliary asset; original scene payload stays untouched',async()=>{
 const f=fixture(),before=JSON.stringify(f.project.project_payload)
 assert.equal((await f.post()).status,200);assert.equal(f.stored.asset_type,'other');assert.equal(f.stored.metadata.ready,false)
 assert.equal((await f.patch('complete')).status,200);assert.equal(f.stored.metadata.ready,true)
 assert.equal(f.stored.metadata.enabled,true);assert.equal(JSON.stringify(f.project.project_payload),before)
 assert.ok(f.updated.filter(r=>r.table==='std_projects').every(r=>Object.keys(r.value).join(',')==='updated_at'))
 assert.equal((await f.patch('disable')).status,200);assert.equal(f.stored.metadata.enabled,false)
 assert.equal(f.count,1)
})
test('ownership, project finality and source checksum are enforced before preparing uploads',async()=>{
 const other=fixture();other.project.employee_email='someone@test';assert.equal((await other.post()).status,404);assert.equal(other.count,0)
 const locked=fixture();locked.project.status='approved';assert.equal((await locked.post()).status,409);assert.equal(locked.count,0)
 const stale=fixture();stale.body.source_state_sha256='c'.repeat(64);assert.equal((await stale.post()).status,422);assert.equal(stale.count,0)
})
