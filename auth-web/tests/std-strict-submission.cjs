const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),load=require('./load-ts-module.cjs')
const identity=load('lib/stdContentIdentity.ts'),policy=load('lib/stdPolicy.ts')
const source=fs.readFileSync('app/api/std/projects/[projectId]/submit/route.ts','utf8')
test('strict submission rejects old scene assets and requires video on selected scenes',async()=>{
 const p={id:'p',employee_email:'owner@test',status:'claimed',topic_queue_id:null,submitted_at:null,project_payload:{script:'new',strict_content_identity:true,structure:{required_video_scene_count:18,motion_graphic_video_scenes:[19,60,70]}},progress_payload:{}}
 const hash=identity.projectContentIdentity(p).script_sha256
 const make=(n,type,sha)=>({id:`${n}-${type}-${sha}`,scene_number:n,asset_type:type,status:'assigned',metadata:{gcs_path:'file',content_identity:{script_sha256:sha}}})
 let assets=[make(19,'video','old'),make(19,'image',hash),make(20,'image',hash)]
 const scenes=[{scene_number:19},{scene_number:20}]
 const db={from(table){const q={select:()=>q,eq:()=>q,order:()=>q,maybeSingle:async()=>({data:p,error:null}),then:(resolve,reject)=>Promise.resolve({data:table==='std_project_scenes'?scenes:[],error:null}).then(resolve,reject)};return q}}
 const mocks={'next/server':{NextResponse:{json:(body,opt)=>({body,status:opt?.status||200})}},'@/lib/supabaseAdmin':{supabaseAdmin:db},
  '@/lib/stdWeb':{requireStdUser:async()=>({ok:true,requester:{email:p.employee_email,user:{id:'u'}}})},
  '@/lib/stdProjectAssets':{loadStdProjectAssets:async()=>({data:assets,error:null})},'@/lib/stdPolicy':policy,
  '@/lib/stdContentIdentity':identity,'@/lib/stdNonverbal':{isNonverbalProject:()=>false},
  '@/lib/stdSubmittedVideoPostwork':{hasAllSceneParallax:()=>false,hasSubmittedVideoPostwork:()=>false},
  '@/lib/stdThumbnailRender':{editableThumbnailError:()=>null},'@/lib/stdLegacySync':{},
  '@/lib/stdRenderQueue':{ensureStdGeneratedSceneAssetsArchived:async(_p,_s,a)=>a},
  '@/lib/stdAeMouth':{},'@/lib/stdSubmissionPipeline':{},'@/lib/stdAeScenePreparation':{preparedAeScenes:()=>new Map()},
  '@/lib/stdMotionAutomation':{motionAutomationEnabled:()=>false},'@/lib/stdProductionEnginePolicy':{productionEngineError:()=>null},
  '@/lib/stdMotionStudio':{motionProductionMethod:()=> 'ae'}}
 const ex={};new Function('exports','require',ts.transpile(source,{module:1,target:7}))(ex,n=>{if(!(n in mocks))throw Error(n);return mocks[n]})
 let response=await ex.POST({}, {params:{projectId:'p'}});assert.equal(response.status,409);assert.deepEqual(response.body.missing_scene_numbers,[19])
 assets.push(make(19,'video',hash));response=await ex.POST({}, {params:{projectId:'p'}});assert.equal(response.status,409);assert.match(response.body.error,/TTS audio/)
})
