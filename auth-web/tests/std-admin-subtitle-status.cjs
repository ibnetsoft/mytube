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
