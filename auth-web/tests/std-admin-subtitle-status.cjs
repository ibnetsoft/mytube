const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),ts=require('typescript'),path=require('path')
function load(name){const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(__dirname,'../lib',name+'.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText)(ex,n=>n.startsWith('./')?load(n.slice(2)):require(n));return ex}
const {subtitleSpeakerProgress,subtitleSpeechChanged}=load('stdSubtitleSpeakerProgress')
test('speaker count includes unsaved AI classification and preserves uncertainty',()=>{
 const rows=[{text:'こんにちは'},{text:'「待って」'},{text:'narration',dialogue_override:false}]
 const parts=new Map([[0,[{dialogue:true,speaker:'A'}]]])
 assert.deepEqual(subtitleSpeakerProgress(rows,parts,[{name:'A'},null,null]),{total:2,confirmed:1})
})
test('style/timing saves preserve completion while text or voice changes invalidate it',()=>{
 const rows=[{text:'Hello',voice_id:'v',start:0,end:2}]
 assert.equal(subtitleSpeechChanged(rows,[{...rows[0],start:1,end:3,font_size:60}]),false)
 assert.equal(subtitleSpeechChanged(rows,[{...rows[0],text:'Changed'}]),true)
 assert.equal(subtitleSpeechChanged(rows,[{...rows[0],voice_id:'other'}]),true)
})
test('saved subtitle completion requires both successful finalization and durable narration',()=>{
 const {savedStdOutputStepStatus}=load('stdOutputStepStatus')
 const p={project_payload:{audio_url:'gcs-audio'},progress_payload:{subtitle_tts_completed:true}}
 assert.equal(savedStdOutputStepStatus(p).isSubtitlesDone,true)
 assert.equal(savedStdOutputStepStatus({...p,progress_payload:{subtitle_tts_completed:false}}).isSubtitlesDone,false)
 assert.equal(savedStdOutputStepStatus({...p,progress_payload:{subtitle_tts_completed:true,script_changed_requires_audio_regeneration:true}}).isSubtitlesDone,false)
})
test('Save + TTS records completion only after both saves succeed in the same project',async()=>{
 const page=fs.readFileSync(path.join(__dirname,'../app/std/page.tsx'),'utf8')
 const a=page.indexOf('    const handleFinalizeSubtitlesAndTts ='),b=page.indexOf('    // 대본 속 인물',a)
 const code=ts.transpileModule(page.slice(a,b)+'; return handleFinalizeSubtitlesAndTts',{compilerOptions:{target:9}}).outputText
 for(const scenario of ['success','save-failed','tts-failed','changed-project']){
  const events=[];const noop=()=>{}
  const context={ttsNoticeCopy:()=>({}),currentLocale:'ko',hasDistinctDialogueVoiceAssignment:()=>true,setMessage:noop,alert:noop,mediaScopeRef:{current:{projectId:'p'}},setGeneratingTts:noop,setHighlightSaveTts:noop,setTtsNotice:noop,selectedProject:{project:{id:'p'}},getProjectSyncedTitle:()=> 'Project',handleSaveSubtitles:async()=>{events.push('save');return scenario!=='save-failed'},generateTts:async()=>{events.push('tts');return scenario!=='tts-failed'},isCurrentMediaScope:()=>scenario!=='changed-project',persistVrewVoiceSubtitles:async(rows,options)=>{assert.equal(options.subtitleTtsCompleted,true);events.push('complete')},speechSubtitlesRef:{current:[]},localizeStdActionError:()=> 'save failed',console:{warn:noop}}
  await new Function(...Object.keys(context),code)(...Object.values(context))()
  assert.deepEqual(events,scenario==='success'?['save','tts','complete']:scenario==='save-failed'?['save']:['save','tts'])
 }
})
