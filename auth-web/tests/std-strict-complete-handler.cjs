const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript')
function fixture(fail){
 const project={id:'project',status:'claimed',updated_at:'v1',project_payload:{strict_content_identity:true,structure:{scenes:[{scene_number:1}]}},progress_payload:{}}
 const claim={content_identity:{asset_type:'image',scene_number:1,script_sha256:'new'}}
 let sceneWrites=0,projectWrites=0,rpcCalls=0
 const asset={id:'asset',asset_type:'image',scene_number:1,status:'assigned',metadata:{gcs_path:'std-projects/project/image.png'}}
 const db={from(table){let field='',op='';const q={select(){return q},eq(k,v){if(k==='metadata->>kind')field='claim';if(k==='metadata->>gcs_path')field='asset';return q},in(){return q},update(){op='update';if(table==='std_project_scenes')sceneWrites++;if(table==='std_projects')projectWrites++;return q},insert(){op='insert';return q},maybeSingle:async()=>({data:table==='std_projects'?project:table==='std_project_scenes'?{id:'scene',scene_number:1}:field==='claim'?{metadata:claim}:field==='asset'?asset:null,error:null}),single:async()=>({data:asset,error:null}),then(resolve){resolve({count:0,data:[],error:null})}};return q},rpc:async(name,args)=>{rpcCalls++;assert.equal(name,'std_attach_revision_asset');assert.equal(args.p_asset_id,'asset');return fail?{error:{message:'Project changed'}}:{data:{success:true}}}}
 const exports={};const js=ts.transpile(fs.readFileSync('app/api/std/projects/[projectId]/assets/complete/route.ts','utf8'),{module:1,target:9})
 new Function('exports','require',js)(exports,name=>{
  if(name==='next/server')return {NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}}
  if(name.includes('stdContentIdentity'))return {projectContentIdentity:()=>({script_sha256:'new'}),assetMatchesContentRevision:()=>true,renderAssetIdentity:()=>({})}
  if(name.includes('stdComic'))return {isComicProject:()=>false}
  if(name.includes('stdAssetEditPolicy'))return {canEditStdAsset:()=>true}
  if(name.includes('stdSubmittedVideoReplacement'))return {queueSubmittedVideoReplacement:async()=>{}}
  if(name.includes('stdReplacedVideoCleanup'))return {cleanupReplacedSceneVideos:async()=>{}}
  if(name.includes('stdAudioMix'))return {audioAssetStorageFields:t=>({asset_type:t,metadata:{}})}
  if(name.includes('supabaseAdmin'))return {supabaseAdmin:db}
  if(name.includes('stdWeb'))return {requireStdUser:async()=>({ok:true,requester:{email:'owner',user:{id:'u'}}})}
  if(name.includes('stdPolicy'))return {strictRevisionSceneUploadAllowed:()=>true,isStdVideoPromptScene:()=>false,isStdRequiredClipScene:()=>false,stdRequiredVideoSceneCount:()=>18}
  if(name.includes('stdLegacySync'))return {syncStdProjectToLegacy:async()=>{}}
  if(name.includes('gcsStorage'))return {isGcsConfiguredAsync:async()=>true,getGcsObjectMetadata:async()=>({size:1,contentType:'image/png'})}
  throw Error(name)
 })
 return {run:()=>exports.POST({json:async()=>({storage_path:'std-projects/project/image.png',asset_type:'image',scene_number:1})},{params:{projectId:'project'}}),counts:()=>({sceneWrites,projectWrites,rpcCalls})}
}
for(const fail of [false,true])test(`strict complete ${fail?'conflict':'success'} does not write scene or project outside atomic RPC`,async()=>{const f=fixture(fail),r=await f.run();assert.equal(r.status,fail?409:200,JSON.stringify(r.body));assert.deepEqual(f.counts(),{sceneWrites:0,projectWrites:0,rpcCalls:1});if(fail)assert.equal(r.body.asset_id,'asset')})
