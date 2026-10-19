const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript')
const load=require('./load-ts-module.cjs'),motion=load('lib/stdMotionStudio.ts'),media=load('lib/stdSceneMedia.ts')
function fixture(){
 const state={auth:true,owned:true,assets:[{id:'image',asset_type:'image',scene_number:1,status:'uploaded',file_name:'source.png',metadata:{gcs_bucket:'test',gcs_path:'source.png'}}],project:{id:'p',status:'draft',project_payload:{render_settings:{motion:{version:1,enabled:true,aspect:'9:16',fps:24,scenes:{'1':{...motion.motionScene(),source:'image'}}}}}}}
 const db={from(table){let row;const query={select(){return query},eq(){return query},insert(value){row=value;return query},async maybeSingle(){return {data:table==='std_projects'?(state.owned?state.project:null):{scene_number:1,duration_seconds:3}}},async single(){state.assets.push(row);return {data:row}}};return query}}
 const exports={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.resolve('app/api/std/projects/[projectId]/motion/route.ts'),'utf8'),{compilerOptions:{module:1,target:7}}).outputText)(exports,name=>{
  if(name==='crypto')return require(name)
  if(name==='next/server')return {NextResponse:{json:(body,options={})=>({body,status:options.status||200})}}
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db}
  if(name.includes('stdWeb'))return {requireStdUser:async()=>state.auth?{ok:true,requester:{email:'owner@example.test'}}:{ok:false,response:{status:401}}}
  if(name.includes('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:state.assets.slice()})}
  if(name.includes('stdMotionStudio'))return motion
  if(name.includes('stdAeScenePreparation'))return load('lib/stdAeScenePreparation.ts')
  if(name.includes('stdSceneMedia'))return media
  throw Error(name)
 })
 return {state,post:body=>exports.POST({json:async()=>({scene_number:1,...body})},{params:{projectId:'p'}}),get:()=>exports.GET({},{params:{projectId:'p'}})}
}
test('preview API enforces session, project ownership and submission lock',async()=>{
 const f=fixture();f.state.auth=false;assert.equal((await f.post()).status,401)
 f.state.auth=true;f.state.owned=false;assert.equal((await f.post()).status,404)
 f.state.owned=true;f.state.project.submitted_at='today';assert.equal((await f.post()).status,400)
 assert.equal(f.state.assets.length,1)
})
test('preview queue freezes exact scene configuration and original asset; retries reuse work',async()=>{
 const f=fixture();assert.equal((await f.post()).status,200)
 const job=f.state.assets[1];assert.equal(job.metadata.input.aspect,'9:16');assert.equal(job.metadata.input.asset.id,'image')
 assert.equal((await f.post()).status,200);assert.equal(f.state.assets.length,2)
 job.metadata.state='ready';job.metadata.gcs_path='preview.mp4';job.metadata.gcs_bucket='test'
 assert.match((await f.get()).body.jobs[0].url,/preview.mp4/)
})
test('director requests remain distinct from ordinary previews and unsupported PSD is blocked',async()=>{
 const f=fixture();await f.post({action:'direction'});assert.equal(f.state.assets[1].metadata.input.task,'direction')
 await f.post();assert.equal(f.state.assets.length,3)
 f.state.project.project_payload.render_settings.motion.scenes[1].source='psd'
 assert.equal((await f.post()).status,400)
})
