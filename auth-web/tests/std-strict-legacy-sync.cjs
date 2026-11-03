const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),load=require('./load-ts-module.cjs')
const identity=load('lib/stdContentIdentity.ts'),policy=load('lib/stdPolicy.ts')
test('legacy sync excludes old revision media and requires selected motion video',async()=>{
 const p={id:'p',user_id:'u',employee_email:'x',status:'claimed',topic_queue_id:null,title:'t',language:'ja',project_payload:{script:'new',strict_content_identity:true,structure:{required_video_scene_count:18,motion_graphic_video_scenes:[19,60,70]}},progress_payload:{}}
 const hash=identity.projectContentIdentity(p).script_sha256
 const asset=(id,n,type,sha)=>({id,scene_number:n,asset_type:type,status:'assigned',metadata:{content_identity:{script_sha256:sha}}})
 const assets=[asset('old',19,'video','old'),asset('new',19,'image',hash),asset('still',20,'image',hash)]
 const scenes=[{scene_number:19,asset_status:'missing'},{scene_number:20,asset_status:'ready'}]
 let saved,filter
 const db={from(table){const q={select:()=>q,eq:()=>q,or:x=>{filter=x;return q},order:()=>q,upsert:async x=>{saved=x;return {error:null}},maybeSingle:async()=>({data:p,error:null}),then:(resolve,reject)=>Promise.resolve({data:table==='std_project_scenes'?scenes:assets,error:null}).then(resolve,reject)};return q}}
 const code=ts.transpile(fs.readFileSync('lib/stdLegacySync.ts','utf8'),{module:1,target:7}),ex={}
 new Function('exports','require',code)(ex,n=>{if(n.includes('supabaseAdmin'))return {supabaseAdmin:db};if(n.includes('stdPolicy'))return policy;if(n.includes('stdContentIdentity'))return identity;throw Error(n)})
 await ex.syncStdProjectToLegacy('p')
 assert.match(filter,/content_revision_backup/)
 assert.equal(saved.project_payload.image_prompts[0].video_url,null)
 assert.match(saved.project_payload.image_prompts[0].image_url,/new/)
 assert.equal(saved.progress_payload.steps.image,false)
 assets.unshift(asset('current',19,'video',hash));await ex.syncStdProjectToLegacy('p');assert.equal(saved.progress_payload.steps.image,true)
})
