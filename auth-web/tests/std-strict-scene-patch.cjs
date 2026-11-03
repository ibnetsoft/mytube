const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), ts=require('typescript')
const identity=require('./load-ts-module.cjs')('lib/stdContentIdentity.ts')
const filename=path.resolve(__dirname,'../app/api/std/projects/[projectId]/route.ts')
const code=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
test('strict scene PATCH ignores stale input URLs and binds only current-revision assets', async()=>{
 for (const withCurrent of [false,true]) {
 const project={id:'p',employee_email:'owner@example.com',status:'claimed',updated_at:'2026-01-01',topic_queue_id:1,
  project_payload:{strict_content_identity:true,script:'new',structure:{scenes:[{scene_number:1,scene_text:'new',image_url:'https://old.example/old.png'}]}},source_payload:{pregenerated_script:'new'},progress_payload:{}}
 const hash=identity.projectContentIdentity(project).script_sha256
 const assets=[{id:'old',asset_type:'image',scene_number:1,status:'uploaded',metadata:{storage_public_url:'https://old.example/old.png'}},
  {id:'new',asset_type:'image',scene_number:1,status:'uploaded',metadata:{storage_public_url:'https://new.example/new.png',content_identity:{script_sha256:hash}}}]
 const state={project,scenes:[{id:'s',project_id:'p',scene_number:1,scene_text:'new',metadata:{}}],assets:withCurrent?assets:assets.slice(0,1)}
 const db={from(table){let patch=null;const q={select(){return q},eq(){return q},in(){return q},is(){return q},order(){return q},
  update(value){patch=value;return q},maybeSingle:async()=>{if(table==='std_projects'&&patch)state.project={...state.project,...patch};return {data:state.project,error:null}},
  then(resolve,reject){if(table==='std_project_scenes'&&patch)state.scenes=state.scenes.map(s=>({...s,...patch}));return Promise.resolve({data:table==='std_project_scenes'?state.scenes:[],error:null}).then(resolve,reject)}};return q},
  storage:{from:()=>({getPublicUrl:()=>({data:{publicUrl:''}})})}}
 const mocks={
  'next/server':{NextResponse:Response},'@/lib/stdAudioAnchors':{preserveAudioAnchors:(_,v)=>v},
  '@/lib/stdContentIdentity':{...identity,persistContentRevision:async()=>{}},'@/lib/stdProjectReadCache':{},
  '@/lib/stdProjectAssets':{loadStdProjectAssets:async()=>({data:state.assets,error:null})},
  '@/lib/stdSubtitleSpeakerProgress':{},'@/lib/stdTemplateOverlayPng':{},'@/lib/stdDialogueSceneIndex':{dialogueSceneIndex:()=>[]},
  '@/lib/stdSubtitleFragments':{},'@/lib/stdSubtitleSaveContext':{},'@/lib/stdSubtitleSceneIntegrity':{},
  '@/lib/stdMotionStudio':{},'@/lib/stdComic':{isComicProject:()=>false},'@/lib/stdProjectEditPolicy':{canEditStdProject:()=>true},
  '@/lib/stdThumbnailRender':{},'@/lib/supabaseAdmin':{supabaseAdmin:db},'@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:project.employee_email}})},
  '@/lib/stdPolicy':{isStdVideoPromptScene:()=>false},'@/lib/stdRenderQueue':{},'@/lib/stdCharacterProtection':{},
  '@/lib/stdSceneMediaUrl':require('./load-ts-module.cjs')('lib/stdSceneMediaUrl.ts'), '@/lib/stdUserWebPayload':{stripPostworkDirection:v=>v},
 }
 const exp={};new Function('exports','require',code)(exp,name=>{if(!(name in mocks))throw Error('unexpected '+name);return mocks[name]})
 const body={allow_scene_update:true,project_payload:{scenes:[{scene_number:1,scene_text:'new',image_prompt:'harbor',image_url:'https://old.example/from-browser.png',metadata:{image_url:'https://old.example/from-browser.png',metadata:{video_url:'https://old.example/video.mp4'}}}]}}
 const response=await exp.PATCH(new Request('https://example.test/api/std/projects/p',{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify(body)}),{params:{projectId:'p'}})
 const expected = withCurrent ? 'https://new.example/new.png' : undefined
 assert.equal(response.status,200);assert.equal(state.scenes[0].metadata.image_url,expected)
 assert.equal(state.scenes[0].metadata.metadata.video_url,undefined)
 assert.equal(state.project.project_payload.structure.scenes[0].image_url,expected)
 }
})
