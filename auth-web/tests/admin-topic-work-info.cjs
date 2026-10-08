const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),ts=require('typescript')
const root=path.resolve(__dirname,'..'),cache={}
function load(file){if(cache[file])return cache[file];const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:1,target:9,jsx:4}}).outputText)(ex,n=>n.startsWith('./')?load('lib/'+n.slice(2)+'.ts'):require(n));return cache[file]=ex}
const {attachTopicWorkInfo}=load('lib/adminTopicWorkInfo.ts'),{speakerCoordinateOverview}=load('lib/stdSpeakerCoordinateOverview.ts'),geometry=load('lib/stdSpeakerGeometry.ts')
const project={id:'p1',topic_queue_id:1,project_payload:{subtitles:[{scene_number:19,dialogue_kind:'dialogue',text:'hello',editor_speaker:{text:'hello',name:'Mother'}},{scene_number:20,dialogue_kind:'dialogue',text:'wait'},{scene_number:20,dialogue_kind:'narration',text:'narrator',dialogue_speaker:'Narrator'}]}}
const image={id:'image',project_id:'p1',asset_type:'image',status:'uploaded',scene_number:19,metadata:{gcs_path:'image.png'}}
const scene=geometry.coordinateScenes(project,[image])[0]
const confirmed={id:'confirmation',project_id:'p1',asset_type:'other',status:'uploaded',metadata:{kind:'speaker_coordinate_confirmation',scene_key:scene.key,results:[{number:19,image_id:'image',source_path:'image.png',source_sha256:'a'.repeat(64),speakers:[{speaker:'Mother',status:'offscreen'}]}]}}
function dbMock(projects,assets,error=false){let reads=0;return{get reads(){return reads},from(table){let range=[0,999];const q={select:()=>q,in:()=>q,neq:()=>q,order:()=>q,or:()=>q,range:(a,b)=>{range=[a,b];return q},then:(a,b)=>{if(table==='std_project_assets')reads++;return Promise.resolve({data:table==='std_projects'?projects:assets.slice(range[0],range[1]+1),error:error?new Error('test read failure'):null}).then(a,b)}};return q}}}
test('admin uses the same coordinate overview and text-matched speaker assignments',async()=>{
 const db=dbMock([project],[image,confirmed]),[topic,empty]=await attachTopicWorkInfo(db,[{id:1},{id:2}]),overview=speakerCoordinateOverview(project,[image,confirmed])
 for(const key of ['count','completed','confirmed','failed','pending'])assert.equal(topic.work_info[key],overview[key])
 assert.deepEqual(topic.work_info.speakerProgress,{total:2,confirmed:1});assert.equal(topic.work_info.confirmed,1);assert.equal(empty.work_info,null)
 assert(!('scenes' in topic.work_info));assert(!('project_payload' in topic.work_info))
})
test('confirmation after the first 1000 assets is read and counted; projects remain separate',async()=>{
 const filler=Array.from({length:1001},(_,i)=>({...image,id:'old'+i,scene_number:1})),db=dbMock([project,{id:'p2',topic_queue_id:2,project_payload:{subtitles:[]}}],[image,...filler,confirmed])
 const rows=await attachTopicWorkInfo(db,[{id:1},{id:2}]);assert.equal(rows[0].work_info.completed,1);assert.equal(rows[1].work_info.completed,0);assert.equal(db.reads,3)
})
test('read failures are explicit instead of showing a false zero or removing the topics',async()=>{
 const original=console.error;console.error=()=>{};try{const rows=await attachTopicWorkInfo(dbMock([],[],true),[{id:1,topic:'keep'}]);assert.equal(rows[0].topic,'keep');assert.equal(rows[0].work_info.error,true)}finally{console.error=original}
})
test('shared status display supports Korean and Thai without raw AE labels',()=>{
 const React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),component=load('components/StdSpeakerWorkInfo.tsx').default
 for(const locale of ['ko','th']){const html=renderToStaticMarkup(React.createElement(component,{locale,data:{count:60,completed:47,confirmed:0,failed:9,pending:4,speakerProgress:{total:183,confirmed:183}}}));assert.match(html,/47\/60/);assert.match(html,/183\/183/);assert.match(html,/AIR STUDIO/);assert.doesNotMatch(html,/\bAE\b/);if(locale==='th')assert.doesNotMatch(html,/[가-힣]/)}
})

test('current project output completion overrides stale false topic flags',async()=>{
 const saved={...project,progress_payload:{tts_completed:true,subtitles_saved:true,thumbnail_completed:true}}
 const [topic]=await attachTopicWorkInfo(dbMock([saved],[image]),[{id:1,progress_payload:{steps:{tts:false,subtitle:false,template:false}}}])
 const {savedStdOutputStepStatus,topicOutputStepDone}=load('lib/stdOutputStepStatus.ts')
 assert.deepEqual(topic.work_info.outputSteps,savedStdOutputStepStatus(saved,[image]))
 for(const key of ['tts','subtitle','template'])assert.equal(topicOutputStepDone(key,topic.work_info.outputSteps,topic.progress_payload.steps),true)
})
test('incomplete project outputs override stale true flags and invalidated audio stays incomplete',()=>{
 const {savedStdOutputStepStatus,topicOutputStepDone}=load('lib/stdOutputStepStatus.ts')
 const incomplete=savedStdOutputStepStatus({progress_payload:{tts_completed:true,script_changed_requires_audio_regeneration:true}})
 for(const key of ['tts','subtitle','template'])assert.equal(topicOutputStepDone(key,incomplete,{tts:true,subtitle:true,template:true}),false)
 assert.equal(topicOutputStepDone('tts',undefined,{tts:true}),true)
 const ready=savedStdOutputStepStatus({project_payload:{subtitles_saved:true}},[
  {id:'audio',asset_type:'audio',status:'uploaded',metadata:{gcs_path:'a.wav'}},
  {id:'thumb',asset_type:'thumbnail',status:'assigned',metadata:{storage_path:'t.png'}}])
 assert.equal(ready.isTtsDone,true);assert.equal(ready.isSubtitlesDone,true);assert.equal(ready.isThumbnailDone,true)
 const notReady=savedStdOutputStepStatus({},[{id:'thumb',asset_type:'thumbnail',status:'failed',metadata:{gcs_path:'old.png'}}])
 assert.equal(notReady.isThumbnailDone,false)
})

test('image status is shared for 12 opening videos and remaining stills, including stale topic flags',async()=>{
 const {savedStdOutputStepStatus,topicOutputStepDone}=load('lib/stdOutputStepStatus.ts'),{summarizeStdProject}=load('lib/stdProjectStepStatus.ts')
 const scenes=Array.from({length:101},(_,i)=>({scene_number:i+1}))
 const p={...project,project_payload:{scenes,subtitles:[]}}
 const media=scenes.map(s=>({id:'media'+s.scene_number,project_id:'p1',scene_number:s.scene_number,asset_type:s.scene_number<=12?'video':'image',status:'uploaded',metadata:{gcs_path:'saved/'+s.scene_number}}))
 const [topic]=await attachTopicWorkInfo(dbMock([p],media),[{id:1,progress_payload:{steps:{image:false}}}])
 assert.equal(topic.work_info.outputSteps.isImageDone,true)
 assert.equal(topicOutputStepDone('image',topic.work_info.outputSteps,{image:false}),true)
 assert.equal(savedStdOutputStepStatus(p,media).uploadedAssetsCount,101)
 assert.equal(summarizeStdProject(p,media).isImageDone,true)
 assert.equal(savedStdOutputStepStatus(p,media.slice(0,-1)).isImageDone,false)
 assert.equal(topicOutputStepDone('image',savedStdOutputStepStatus(p,media.slice(1)),{image:true}),false)
 assert.equal(savedStdOutputStepStatus(p,[{...media[0],asset_type:'image'},...media.slice(1)]).isImageDone,false)
})
