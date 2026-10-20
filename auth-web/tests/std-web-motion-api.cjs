const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript'),crypto=require('node:crypto')
function fixture(options={}){
 const state={providerPosts:0,filters:[],writes:[],assets:options.assets||[],project:{id:'p',employee_email:'owner@example.com',status:'in_progress',updated_at:'version',project_payload:{render_settings:{motion:{production_method:'motion_studio'}}},...options.project}}
 const db={from(table){let action='select',body
  const q={select(){return q},eq(k,v){state.filters.push([table,k,v]);return q},order(){return q},update(b){action='update';body=b;return q},insert(b){action='insert';body=b;return q},maybeSingle(){return Promise.resolve({data:table==='std_projects'?(options.missing?null:state.project):null})},then(resolve){if(action!=='select')state.writes.push({table,action,body});return Promise.resolve({data:table==='std_project_scenes'?[{scene_number:1,scene_title:'scene'}]:null,error:table==='std_project_assets'&&action==='insert'&&options.reservationConflict?{code:'23505'}:null}).then(resolve)}};return q}}
 const ex={},code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../app/api/std/projects/[projectId]/web-motion/route.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText
 new Function('exports','require',code)(ex,name=>{
  if(name==='crypto')return crypto
  if(name==='next/server')return {NextResponse:{json:(data,init)=>Response.json(data,init)}}
  if(name.endsWith('supabaseAdmin'))return {supabaseAdmin:db}
  if(name.endsWith('stdWeb'))return {requireStdUser:async()=>options.unauthorized?{ok:false,response:Response.json({error:'unauthorized'},{status:401})}:{ok:true,requester:{email:'owner@example.com'}}}
  if(name.endsWith('stdProjectAssets'))return {loadStdProjectAssets:async()=>({data:state.assets})}
  if(name.endsWith('stdContentIdentity'))return {selectNarrationAsset:()=>{throw Error('final voice required')}}
  if(name.endsWith('stdLipSync'))return {lipSyncPlan:()=>{},lipSyncSceneStarts:()=>[0]}
  if(name.endsWith('stdAeScenePreparation'))return {aeSceneSources:()=>new Map()}
  if(name.endsWith('stdWebMotionSources'))return require('./load-ts.cjs')(path.resolve(__dirname,'../lib/stdWebMotionSources.ts'))
  if(name.endsWith('stdMotionStudio'))return {motionProductionMethod:p=>p.project_payload?.render_settings?.motion?.production_method==='ae'?'ae':'motion_studio'}
  if(name.endsWith('stdAudioMix'))return {backgroundWindow:()=>({valid:true,start:0,end:1}),backgroundVolume:()=>.08}
  if(name.endsWith('stdSfxCues'))return {resolveSfxCues:()=>[],sfxNeedsReview:()=>false}
  if(name.endsWith('stdTemplateOverlayPng'))return {templateOverlayPng:async()=>null}
  if(name.endsWith('stdSceneMedia'))return {storageSourceForAsset:a=>a?{gcsBucket:'bucket',gcsPath:'source.png'}:null}
  if(name.endsWith('stdVideoModelStore'))return {selectedVideoModel:async()=>({config:{id:'model'},secret:'never-expose',fingerprint:'model-fingerprint'})}
  if(name.endsWith('gcsStorage'))return {getGcsObjectMetadata:async()=>({size:options.objectSize??5,contentType:'image/png'}),downloadGcsObjectViaSignedUrl:async()=>({buffer:Buffer.from('image')}),createGcsSignedReadUrl:async()=>'https://storage.googleapis.com/test'}
  if(name.endsWith('stdMotionVideoProvider'))return {createProviderVideo:async()=>{state.providerPosts++;if(options.ambiguous)throw Error('network');return {id:'request',status_url:'https://queue.fal.run/status'}},pollProviderVideo:async()=>({state:'pending'})}
  throw Error(name)
 });return {ex,state}
}
const req=body=>new Request('http://local/api/std/projects/p/web-motion',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)})
const params={params:{projectId:'p'}},source={id:'source',project_id:'p',scene_number:1,asset_type:'original',status:'uploaded',file_name:'source.png',mime_type:'image/png'}
const generation={action:'generate',mode:'hybrid',source_asset_id:'source',scene_number:1,prompt:'gentle motion',duration:3}
test('web motion authenticates before reading assets and scopes owner lookup',async()=>{
 let f=fixture({unauthorized:true});assert.equal((await f.ex.GET(new Request('http://local'),params)).status,401);assert.equal(f.state.filters.length,0)
 f=fixture({missing:true});assert.equal((await f.ex.GET(new Request('http://local'),params)).status,404);assert.ok(f.state.filters.some(x=>x[1]==='employee_email'&&x[2]==='owner@example.com'))
 f=fixture();const data=await (await f.ex.GET(new Request('http://local'),params)).json();assert.match(data.audio_error,/voice/);assert.equal(data.audio,null)
})
test('web mode and closed projects never call a paid video provider',async()=>{
 for(const project of [{},{status:'approved'},{submitted_at:'date'}]){const f=fixture({project,assets:[source]});assert.equal((await f.ex.POST(req({...generation,mode:'web'}),params)).status,400);assert.equal(f.state.providerPosts,0)}
})
test('paid creation reserves an id before provider POST, never resubmits ambiguous intent',async()=>{
 const f=fixture({assets:[source],ambiguous:true}),response=await f.ex.POST(req(generation),params)
 assert.equal(response.status,409);assert.equal(f.state.providerPosts,1);assert.equal(f.state.writes[0].body.metadata.state,'creating');assert.equal(f.state.writes.at(-1).body.metadata.state,'needs_reconcile')
 const conflict=fixture({assets:[source],reservationConflict:true});assert.equal((await conflict.ex.POST(req(generation),params)).status,200);assert.equal(conflict.state.providerPosts,0)
})
test('same source pixels reserve the same paid request even after repeated source uploads',async()=>{
 const a=fixture({assets:[source]}),b=fixture({assets:[{...source,id:'source-copy'}]})
 await a.ex.POST(req(generation),params);await b.ex.POST(req({...generation,source_asset_id:'source-copy'}),params)
 assert.equal(a.state.writes[0].body.id,b.state.writes[0].body.id)
 assert.equal(JSON.stringify(await (await a.ex.POST(req({action:'poll',scene_number:1,job_id:'missing'}),params)).json()).includes('never-expose'),false)
})
test('review cannot register a scene clip or an unrelated uploaded video as a final',async()=>{
 for(const asset of [{...source,asset_type:'video',file_name:'other.mp4',scene_number:null},{...source,asset_type:'video',file_name:'motion-web-final-x.mp4'}]){const f=fixture({assets:[asset]});assert.equal((await f.ex.POST(req({action:'review',asset_id:source.id}),params)).status,400);assert.equal(f.state.writes.length,0)}
})
test('ordinary submission cannot send a saved web project back to local AE or legacy render queues',async()=>{
 const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../app/api/std/projects/[projectId]/submit/route.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText
 for(const mode of ['web','hybrid']){
  const ex={},project={id:'p',status:'in_progress',project_payload:{render_settings:{motion:{enabled:true,web:{mode,inserts:{}}}}}}
  const query={select(){return query},eq(){return query},maybeSingle:async()=>({data:project})}
  new Function('exports','require',code)(ex,name=>{
   if(name==='next/server')return {NextResponse:{json:(data,init)=>Response.json(data,init)}}
   if(name.endsWith('supabaseAdmin'))return {supabaseAdmin:{from:()=>query}}
   if(name.endsWith('stdWeb'))return {requireStdUser:async()=>({ok:true,requester:{email:'owner@example.com'}})}
   if(name.endsWith('stdMotionStudio'))return {motionProductionMethod:()=> 'motion_studio'}
   return new Proxy({},{get(){throw Error('Web submission reached a legacy worker dependency')}})
  })
  const response=await ex.POST(req({}),params);assert.equal(response.status,409);assert.equal((await response.json()).code,'web_motion_export_required')
 }
})
test('AE-selected projects cannot accidentally create a paid web job or submit browser output',async()=>{
 const f=fixture({project:{project_payload:{render_settings:{motion:{production_method:'ae',web:{mode:'hybrid',inserts:{}}}}}},assets:[source]})
 for(const body of [generation,{action:'review',asset_id:'source'}]){const response=await f.ex.POST(req(body),params);assert.equal(response.status,400);assert.match((await response.json()).error,/추가 옵션/)}
 assert.equal(f.state.providerPosts,0);assert.equal(f.state.writes.length,0)
})
test('reviewed PSD packages already attached to scene assets are served with ownership and byte-hash checks',async()=>{
 const asset={...source,asset_type:'image',file_name:'scene.png',metadata:{psd_layer_asset:{status:'ready',qa_status:'approved',gcs_bucket:'owned-bucket',gcs_path:'std-projects/p/scene-1.psd',sha256:crypto.createHash('sha256').update('image').digest('hex')}}}
 const f=fixture({assets:[asset]}),data=await (await f.ex.GET(new Request('http://local'),params)).json();assert.equal(data.scenes[0].source.kind,'psd');assert.match(data.scenes[0].source.url,/web-motion\?psd=source/)
 const request=new Request('http://local?psd=source'),file=await f.ex.GET(request,params);assert.equal(file.status,200);assert.equal(await file.text(),'image');assert.equal(file.headers.get('content-type'),'image/vnd.adobe.photoshop')
 for(const settings of [{gcs_path:'std-projects/other/scene.psd'},{sha256:'0'.repeat(64)},{qa_status:'pending'}]){const bad=fixture({assets:[{...asset,metadata:{psd_layer_asset:{...asset.metadata.psd_layer_asset,...settings}}}]});assert.equal((await bad.ex.GET(request,params)).status,400)}
 const tooLarge=fixture({assets:[asset],objectSize:151*1024*1024});assert.equal((await tooLarge.ex.GET(request,params)).status,400)
 const unauthorized=fixture({assets:[asset],unauthorized:true});assert.equal((await unauthorized.ex.GET(request,params)).status,401);assert.equal(f.state.writes.length,0)
})
test('owned project prepared originals fill scenes without uploaded assets and retain immutable source hashes',async()=>{
 const sha='a'.repeat(64),project={id:'p',employee_email:'owner@example.com',status:'in_progress',project_payload:{structure:{scenes:[{scene_number:1,metadata:{cowork_image_asset:{gcs_bucket:'air-studio-prod',gcs_path:`topics/prepared/0123456789abcdef/images/scene-001-${sha.slice(0,16)}.png`,sha256:sha}}}]}}};const f=fixture({project});const response=await f.ex.GET(new Request('https://test/web-motion'),{params:{projectId:'p'}});assert.equal(response.status,200);const body=await response.json();assert.equal(body.scenes[0].source.kind,'image');assert.equal(body.scenes[0].source.sha256,sha);assert.match(body.scenes[0].source.url,/^\/api\/std\/assets\/gcs-file\?/)
 const {preparedWebImage}=require('./load-ts.cjs')(path.resolve(__dirname,'../lib/stdWebMotionSources.ts'));assert.equal(preparedWebImage(project,{scene_number:1,project_id:'foreign'}),null);const bad=structuredClone(project);bad.project_payload.structure.scenes[0].metadata.cowork_image_asset.gcs_path='https://outside/scene.png';assert.throws(()=>preparedWebImage(bad,{scene_number:1,project_id:'p'}))
})
