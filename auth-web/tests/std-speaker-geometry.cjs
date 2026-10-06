const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript'),crypto=require('crypto')
const root=path.resolve(__dirname,'..'),cache={}
function load(file,deps={}){if(!Object.keys(deps).length&&cache[file])return cache[file];const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:1,target:7}}).outputText)(ex,n=>n in deps?deps[n]:n.startsWith('./')?load('lib/'+n.slice(2)+'.ts'):require(n));if(!Object.keys(deps).length)cache[file]=ex;return ex}
const lib=load('lib/stdSpeakerGeometry.ts'),id='e9233112-f0d7-4b35-91bf-2f892844eb30',original=Buffer.from('original test image bytes'),imageHash=crypto.createHash('sha256').update(original).digest('hex')
function fixture(){const project={id,project_payload:{subtitles:[{scene_number:19,dialogue_kind:'dialogue',dialogue_speaker:'娘',text:'はい'}]}};const image={id:'image19',asset_type:'image',status:'uploaded',scene_number:19,metadata:{gcs_path:'original.png',gcs_bucket:'bucket'}};const cast=lib.coordinateCast(project),scene=lib.coordinateScenes(project,[image])[0],speakers=[{speaker:'娘',status:'visible',confidence:.99,face_box:[.2,.2,.6,.6],mouth_box:[.4,.4,.45,.43]}];const result={number:19,image_id:image.id,source_path:'original.png',source_sha256:imageHash,speakers};return{project,image,scene,cast,speakers,result}}
test('manual geometry validates containment, size, overlap and all speakers',()=>{
 const f=fixture();assert.equal(lib.validateSpeakerGeometry(f.speakers,['娘'])[0].confidence,1)
 for(const patch of [{face_box:[.1,.1,.2,.2]},{mouth_box:[.1,.1,.8,.8]},{mouth_box:[NaN,.4,.45,.43]},{status:'uncertain'}])assert.throws(()=>lib.validateSpeakerGeometry([{...f.speakers[0],...patch}],['娘']))
 assert.throws(()=>lib.validateSpeakerGeometry([...f.speakers,{...f.speakers[0],speaker:'母'}],['娘','母']),/겹칠/)
 assert.throws(()=>lib.validateSpeakerGeometry([],['娘']))
 assert.equal(lib.validateSpeakerGeometry([{speaker:'娘',status:'offscreen'}],['娘'])[0].status,'offscreen')
})
test('completed scenes are reusable when another AI scene failed',()=>{
 const f=fixture(),job={status:'uploaded',metadata:{kind:'ae_speaker_coordinates',state:'needs_review',input:{cast_key:JSON.stringify(f.cast)},results:[f.result]}}
 assert.equal(lib.savedSpeakerGeometry([job],f.cast,f.scene).origin,'ai')
 job.metadata.results[0].speakers[0].confidence=.7;assert.equal(lib.savedSpeakerGeometry([job],f.cast,f.scene),null)
})
test('human confirmation wins over later AI and survives text edits but not source/cast/speaker changes',()=>{
 const f=fixture(),manual={status:'uploaded',updated_at:'2020',metadata:{kind:'speaker_coordinate_confirmation',scene_key:f.scene.key,results:[f.result]}}
 const ai={status:'uploaded',updated_at:'2030',metadata:{kind:'ae_speaker_coordinates',input:{cast_key:JSON.stringify(f.cast)},results:[f.result]}}
 assert.equal(lib.savedSpeakerGeometry([ai,manual],f.cast,f.scene).origin,'user')
 f.scene.rows[0].text='edited';assert.equal(lib.savedSpeakerGeometry([manual],f.cast,f.scene).origin,'user')
 for(const mutate of [s=>s.image.id='new',s=>s.image.metadata.gcs_path='changed.png',s=>s.rows[0].speaker='other']){const s=structuredClone(f.scene);mutate(s);assert.equal(lib.savedSpeakerGeometry([manual],f.cast,s),null)}
 assert.equal(lib.savedSpeakerGeometry([manual],{...f.cast,main:{name:'other'}},f.scene),null)
})
function apiFixture({owned=true,authorized=true}={}){
 const f=fixture(),assets=[f.image],writes=[],filters=[]
 const db={from(table){let insertion;const result=()=>({data:insertion?{id:'saved',...insertion}:table==='std_projects'?(owned?f.project:null):assets,error:null});const q={select:()=>q,eq:(...args)=>{filters.push([table,...args]);return q},in:()=>q,order:()=>q,insert:value=>{insertion=value;writes.push(value);return q},maybeSingle:async()=>result(),single:async()=>result(),then:(a,b)=>Promise.resolve(result()).then(a,b)};return q}}
 const api=load('app/api/std/projects/[projectId]/speaker-coordinates/route.ts',{'next/server':{NextResponse:Response},'@/lib/supabaseAdmin':{supabaseAdmin:db},'@/lib/stdWeb':{requireStdUser:async()=>authorized?{ok:true,requester:{email:'owner@example.com'}}:{ok:false,response:Response.json({error:'Authentication required'},{status:401})}},'@/lib/gcsStorage':{downloadGcsObject:async ref=>{assert.deepEqual(ref,{bucket:'bucket',objectPath:'original.png'});return original}},'@/lib/stdSceneImageDownload':{readSceneImage:async()=>({buffer:original,contentType:'image/png'})},'@/lib/stdSpeakerGeometry':lib})
 const request=(body={},method='POST')=>new Request('https://studio.example/api/std/projects/'+id+'/speaker-coordinates',{method,headers:{'content-type':'application/json'},body:JSON.stringify(body)})
 return{...f,api,writes,filters,request,params:{params:{projectId:id}}}
}
test('status reads never enqueue AI; explicit analysis queues only the chosen scene',async()=>{
 const f=apiFixture();const status=await f.api.POST(f.request(),f.params);assert.equal(status.status,200);assert.equal((await status.json()).count,1);assert.equal(f.writes.length,0)
 await f.api.POST(f.request({action:'analyze',sceneNumber:19}),f.params);assert.equal(f.writes.length,1);assert.equal(f.writes[0].metadata.input.scenes.length,1)
})
test('user saves without AI worker, preserving source hash and ownership',async()=>{
 const f=apiFixture();const response=await f.api.PATCH(f.request({sceneNumber:19,sceneKey:f.scene.key,imageSha256:imageHash,speakers:f.speakers},'PATCH'),f.params)
 assert.equal(response.status,200);const data=await response.json();assert.equal(data.completed,1);assert.equal(data.confirmed,1);assert.equal(f.writes[0].metadata.kind,'speaker_coordinate_confirmation');assert.equal(f.writes[0].metadata.results[0].source_sha256,imageHash)
 assert(f.filters.some(([table,key,value])=>table==='std_projects'&&key==='employee_email'&&value==='owner@example.com'))
})
test('stale image/key, missing authentication and other projects cannot be confirmed',async()=>{
 for(const patch of [{sceneKey:'stale'},{imageSha256:'changed'}]){const f=apiFixture();const r=await f.api.PATCH(f.request({sceneNumber:19,sceneKey:f.scene.key,imageSha256:imageHash,speakers:f.speakers,...patch},'PATCH'),f.params);assert.equal(r.status,409);assert.equal(f.writes.length,0)}
 for(const [options,status] of [[{owned:false},404],[{authorized:false},401]]){const f=apiFixture(options);assert.equal((await f.api.PATCH(f.request({},'PATCH'),f.params)).status,status);assert.equal(f.writes.length,0)}
})
