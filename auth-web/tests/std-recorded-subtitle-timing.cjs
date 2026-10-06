const test=require('node:test'), assert=require('node:assert/strict'), ts=require('typescript'),fs=require('node:fs'),path=require('node:path')
const mod={}
new Function('exports',ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../lib/stdRecordedSubtitleTiming.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(mod)
test('recorded timing replaces all stale time fields and preserves edits',()=>{
 const row={text:'a',voice_id:'v',start:45,start_num:45,start_time:'45',end:50,restored_audio_pending:true,translation:'번역',sfx_cues:['keep']}
 const [result]=mod.applyRecordedSubtitleTiming([row],[{text:'a',voice_id:'v',start:63.712,end:66.424}])
 assert.equal(result.start,63.712);assert.equal(result.start_num,63.712);assert.equal(Number(result.start_time),63.712)
 assert.equal(result.end,66.424);assert.equal(result.restored_audio_pending,undefined);assert.equal(result.translation,'번역');assert.deepEqual(result.sfx_cues,['keep']);assert.equal(row.start,45)
})
test('changed words or voice must not be silently aligned',()=>{
 assert.throws(()=>mod.applyRecordedSubtitleTiming([{text:'changed',voice_id:'v'}],[{text:'old',voice_id:'v',start:0,end:1}]))
 assert.throws(()=>mod.applyRecordedSubtitleTiming([{text:'a',voice_id:'new'}],[{text:'a',voice_id:'old',start:0,end:1}]))
})
