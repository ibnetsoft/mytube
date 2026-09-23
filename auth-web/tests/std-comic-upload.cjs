const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const path = require('node:path')
const compile = file => ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText
const cache = {}
function lib(name) {
 if(cache[name]) return cache[name]
 const exports={};cache[name]=exports
 new Function('exports','require',compile(path.join(__dirname,'../lib',name+'.ts')))(exports,id=>id.endsWith('.json')?require(path.join(__dirname,'../lib',id)):lib(path.basename(id)))
 return exports
}
let project, authorized = true, filters = [], signed = 0
const exportsRoute={}
new Function('exports','require',compile(path.join(__dirname,'../app/api/std/projects/[projectId]/assets/init/route.ts')))(exportsRoute,id=>{
 if(id==='next/server') return {NextResponse:{json:(body,opts={})=>({body,status:opts.status||200})}}
 if(id.endsWith('stdWeb')) return {requireStdUser:async()=>authorized?{ok:true,requester:{email:'owner@test.invalid'}}:{ok:false,response:{status:401}}}
 if(id.endsWith('supabaseAdmin')) return {supabaseAdmin:{from:()=>({select(){return this},eq(k,v){filters.push([k,v]);return this},async maybeSingle(){return {data:project}}})}}
 if(id.endsWith('gcsStorage')) return {sanitizeGcsObjectName:s=>s,buildStdGcsObjectPath:()=> 'test/file.png',isGcsConfiguredAsync:async()=>true,createGcsSignedUploadUrl:async()=>{signed++;return {signedUrl:'https://example.invalid/upload',bucket:'test'}}}
 return lib(path.basename(id))
})
const call=(scene=1,type='image')=>exportsRoute.POST(new Request('https://test.invalid',{method:'POST',body:JSON.stringify({asset_type:type,mime_type:type==='video'?'video/mp4':'image/png',file_name:type==='video'?'a.mp4':'a.png',scene_number:scene,comic:{version:1,mode:'comic'}})}),{params:{projectId:'p'}})
;(async()=>{
 project={id:'p',status:'in_progress',project_payload:{}}
 assert.equal((await call()).status,422,'standard hook remains protected even if caller supplies mode')
 assert.equal((await call(13)).status,422,'standard generated scenes remain protected')
 project.project_payload.render_settings={comic:{version:1,mode:'comic'}}
 assert.equal((await call()).status,200)
 assert.equal((await call(13)).status,200)
 project.project_payload.render_settings.comic.mode='moving_comic'
 assert.equal((await call(13,'video')).status,200,'manual clips are accepted after the opening twelve scenes')
 assert(filters.some(([k,v])=>k==='employee_email'&&v==='owner@test.invalid'))
 project.status='approved'; assert.equal((await call()).status,409)
 project=null; assert.equal((await call()).status,404)
 authorized=false; assert.equal((await call()).status,401)
 assert.equal(signed,3)
 console.log('PASS: upload opt-in uses persisted owned project; standard restrictions and auth remain intact')
})().catch(e=>{console.error(e);process.exitCode=1})
