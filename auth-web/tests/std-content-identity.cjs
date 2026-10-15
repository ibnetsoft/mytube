const test = require('node:test'), assert = require('node:assert/strict')
const load = require('./load-ts-module.cjs')
const lib = load('lib/stdContentIdentity.ts')
function fixture() {
 const rows = [{text:'最初。', start:0, end:3, voice_id:'v', scene_number:1}, {text:'最後。', start:3, end:8, voice_id:'v', scene_number:2}]
 const project = {id:'p', topic_queue_id:3373, project_payload:{script:'最初。\n最後。', subtitles:rows, audio_url:'/audio?assetId=original'}, progress_payload:{tts_asset_id:'original'}}
 const audio = {id:'original', project_id:'p', asset_type:'audio', status:'uploaded', metadata:{subtitle_timeline:structuredClone(rows), duration_seconds:8}}
 return {project, audio, rows}
}
test('uses explicit finalized audio, regardless of order; never guesses among versions', () => {
 const f=fixture(), other={...f.audio,id:'expanded'}
 assert.equal(lib.selectNarrationAsset(f.project,[other,f.audio]).id,'original')
 delete f.project.progress_payload.tts_asset_id; delete f.project.project_payload.audio_url
 assert.throws(()=>lib.selectNarrationAsset(f.project,[other,f.audio]), /확정 음성/)
})
test('conflicting audio URL and saved ID cannot silently select either recording', () => {
 const f=fixture(); f.project.project_payload.audio_url='/audio?assetId=expanded'
 assert.throws(()=>lib.selectNarrationAsset(f.project,[f.audio]), /서로 다릅니다/)
})
test('legacy original recording is checked by its own transcript, not given a new birth revision', () => {
 const f=fixture(); const r=lib.assertNarrationIdentity(f.project,f.audio,f.rows)
 assert.equal(r.duration_seconds,8); assert.equal(r.verification,'legacy_recorded_timeline')
 assert.equal(f.audio.metadata.content_identity,undefined)
})
test('expanded script with original recording fails even without mouth effects enabled', () => {
 const f=fixture(); f.project.project_payload.script += '追加された別の話。'
 assert.throws(()=>lib.assertNarrationIdentity(f.project,f.audio,f.rows), /大本|대본/)
})
test('wrong text, voice, number, time or duration in captions is rejected', () => {
 for(const mutate of [f=>f.rows[0].text='別の話', f=>f.rows[0].voice_id='other', f=>f.rows.pop(), f=>f.rows[1].end=34, f=>f.audio.metadata.duration_seconds=34]) {
  const f=fixture();mutate(f);assert.throws(()=>lib.assertNarrationIdentity(f.project,f.audio,f.rows), /불일치/)
 }
})
test('generation receipts cannot be relabelled after the script changes', () => {
 const f=fixture(); f.audio.metadata.content_identity=lib.assetContentIdentity(f.project,{type:'audio',timeline:f.rows})
 f.project.project_payload.script='別の話'; f.project.project_payload.subtitles=[{...f.rows[0],text:'別の話'}]
 assert.throws(()=>lib.assertNarrationIdentity(f.project,f.audio,f.project.project_payload.subtitles),/다른 대본/)
})
test('storage provenance detects another topic despite a matching database project ID', () => {
 const f=fixture();f.audio.metadata.gcs_path='topics/9999/voice.mp3'
 assert.throws(()=>lib.assertAssetScope(f.project,f.audio), /토픽 번호/)
 f.audio.metadata.gcs_path='std-projects/other/audio.mp3'; assert.throws(()=>lib.assertAssetScope(f.project,f.audio), /프로젝트 번호/)
})
test('images can survive narration edits only when their original visual inputs still match', () => {
 const f=fixture(),scene={id:'s1',scene_number:1,image_prompt:'girl'}
 const image={id:'img',project_id:'p',scene_id:'s1',scene_number:1,asset_type:'image',metadata:{content_identity:lib.assetContentIdentity(f.project,{type:'image',scene})}}
 f.project.project_payload.script='new narration'
 assert.doesNotThrow(()=>lib.renderAssetIdentity(f.project,scene,image,'original'))
 assert.throws(()=>lib.renderAssetIdentity(f.project,{...scene,image_prompt:'different topic'},image,'original'),/프롬프트/)
 assert.throws(()=>lib.renderAssetIdentity(f.project,{...scene,id:'other'},image,'original'),/씬 자산/)
})
test('mouth video with old audio parent is rejected, including legacy outputs', () => {
 const f=fixture(),scene={scene_number:1}
 const video={project_id:'p',scene_number:1,asset_type:'video',metadata:{ae_mouth_fingerprint:'old',source_audio_id:'expanded'}}
 assert.throws(()=>lib.renderAssetIdentity(f.project,scene,video,'original'),/다른 확정 음성/)
})
test('revision changes preserve previous identity; timing-only edits do not change script revision', () => {
 const f=fixture();let p=lib.bindProjectContent(f.project,f.project.project_payload)
 const first=p.content_identity.script_revision
 let next=lib.bindProjectContent({...f.project,project_payload:p},{...p,subtitles:[{...p.subtitles[0],end:4}]})
 assert.equal(next.content_identity.script_revision,first)
 next=lib.bindProjectContent({...f.project,project_payload:p},{...p,script:'new'})
 assert.equal(next.content_revision_history[0].script_revision,first)
})
test('zero-duration scenes are removed without changing the original narration clock', () => {
 const config={audio_duration:8,images:['one','silent','two'],image_timing_starts:[0,3,3],scene_numbers:[1,2,3],
  image_effects:['a','b','c'],render_settings:{scene_motion_speeds:[1,1,1],timing_locked_indices:[0,2]},
  asset_manifest:{files:[{asset_type:'image',scene_number:1},{asset_type:'image',scene_number:2},{asset_type:'image',scene_number:3}]}}
 const normalized=lib.finalizeRecordedRenderConfig(config)
 assert.deepEqual(normalized.scene_numbers,[1,3]);assert.deepEqual(normalized.image_timing_starts,[0,3])
 assert.equal(normalized.audio_duration,8);assert.equal(normalized.asset_manifest.files.length,2)
 assert.deepEqual(normalized.render_settings.timing_locked_indices,[0,1])
 assert.throws(()=>lib.finalizeRecordedRenderConfig({...config,image_timing_starts:[0,7,0]}),/시작 시간/)
})
