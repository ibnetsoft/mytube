const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript'),crypto=require('node:crypto')
const source=Buffer.from('scene-image'),imageSha=crypto.createHash('sha256').update(source).digest('hex'),audioSha='b'.repeat(64),roles=['mouth_closed','mouth_half','mouth_open','blink','hair']
function fixture(options={}){
 const image={id:'image',project_id:'p',scene_number:1,asset_type:'image',status:'uploaded',created_at:'2026-01-02',metadata:{gcs_bucket:'b',gcs_path:'image'}}
 const audio={id:'audio',project_id:'p',scene_number:null,asset_type:'audio',status:'uploaded',created_at:'2026-01-01',metadata:{sha256:audioSha,subtitle_timeline:[{text:'대사',start:0,end:5}]}}
 const bg={id:'bg',project_id:'p',scene_number:1,asset_type:'other',status:'uploaded',metadata:{kind:'region_layer_upload',role:'background',imageId:'image',imageSha256:imageSha,sha256:'c'.repeat(64)}}
 const patches=roles.map(role=>({id:role,project_id:'p',scene_number:1,asset_type:'other',status:'uploaded',created_at:'2026-01-01',metadata:{kind:'motion2d_patch',role,imageId:'image',imageSha256:imageSha,sha256:'d'.repeat(64)}}))
 const state={writes:[],assets:[image,audio,bg,...patches].filter(x=>x.id!==options.missing),project:{id:'p',status:'in_progress',project_payload:{subtitles:[]},...options.project}}
 const db={from(table){let body;const q={select(){return q},eq(){return q},order(){return q},insert(v){body=v;return q},single:async()=>{state.writes.push(body);return {data:{id:body.id}}},maybeSingle:async()=>({data:table==='std_projects'?state.project:null}),then(resolve){return Promise.resolve({data:table==='std_project_scenes'?[{id:'scene',scene_number:1}]:[]}).then(resolve)}};return q}}
 const ex={},code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../app/api/std/projects/[projectId]/motion2d-render/route.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText
 new Function('exports','require',code)(ex,name=>{if(name==='crypto')return crypto;if(name==='next/server')return {NextResponse:{json:(d,i)=>Response.json(d,i)}};if(name.endsWith('supabaseAdmin'))return {supabaseAdmin:db};if(name.endsWith('stdWeb'))return {requireStdUser:async()=>options.unauthorized?{ok:false,response:Response.json({}, {status:401})}:{ok:true,requester:{email:'owner'}}};if(name.endsWith('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:state.assets})};if(name.endsWith('stdContentIdentity'))return {selectNarrationAsset:()=>audio,assertNarrationIdentity:()=>{}};if(name.endsWith('stdLipSync'))return {lipSyncPlan:()=>[],lipSyncSceneStarts:()=>[0]};if(name.endsWith('stdSpeakerGeometry'))return {coordinateSource:()=>({bucket:'b',path:'image'})};if(name.endsWith('gcsStorage'))return {downloadGcsObject:async()=>source,createGcsSignedReadUrl:async()=>'/video'};throw Error(name)})
 return {ex,state}
}
const params={params:{projectId:'p'}},body={scene:1,imageId:'image',imageSha256:imageSha,backgroundAssetId:'bg'}
const req=b=>new Request('http://local',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})
test('queues the latest five scene-bound patches with the finalized audio only for owner',async()=>{
 const denied=fixture({unauthorized:true});assert.equal((await denied.ex.POST(req(body),params)).status,401);assert.equal(denied.state.writes.length,0)
 for(const options of [{missing:'hair'},{missing:'bg'},{project:{submitted_at:'now'}}]){const f=fixture(options);assert.equal((await f.ex.POST(req(body),params)).status,400);assert.equal(f.state.writes.length,0)}
 const f=fixture(),r=await f.ex.POST(req(body),params);assert.equal(r.status,200);assert.equal(f.state.writes.length,1);const meta=f.state.writes[0].metadata;assert.equal(meta.kind,'motion2d_render');assert.equal(meta.input.audio.id,'audio');assert.deepEqual(Object.keys(meta.input.patches),roles);assert.equal(meta.input.audio_start,0)
 f.state.assets.push({...f.state.writes[0],created_at:'2026-02-01'});const again=await f.ex.POST(req(body),params);assert.equal((await again.json()).id,f.state.writes[0].id);assert.equal(f.state.writes.length,1)
})
test('ready previews become stale when a newer patch is saved',async()=>{
 const f=fixture();await f.ex.POST(req(body),params);const written=f.state.writes[0]
 const job={...written,created_at:'2026-03-01',metadata:{...written.metadata,state:'ready',result:{gcs_bucket:'b',gcs_path:'render'}}};f.state.assets.push(job)
 const get=()=>new Request(`http://local?scene=1&id=${job.id}`)
 let response=await f.ex.GET(get(),params);assert.equal((await response.json()).state,'ready')
 response=await f.ex.GET(new Request(`http://local?scene=1&id=${job.id}&backgroundId=other`),params);assert.equal((await response.json()).state,'stale')
 const latest={...f.state.assets.find(a=>a.id==='hair'),id:'new-hair',created_at:'2026-04-01'};f.state.assets.push(latest)
 response=await f.ex.GET(get(),params);const result=await response.json();assert.equal(result.state,'stale');assert.equal(result.url,null)
})
