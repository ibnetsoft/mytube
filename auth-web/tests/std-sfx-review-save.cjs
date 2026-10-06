const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');const exports_={};new Function('exports',ts.transpileModule(fs.readFileSync('auth-web/lib/stdProjectEditPolicy.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(exports_);const body={render_settings_scope:'audio',project_payload:{render_settings:{sfx_cues:[{id:'cue',enabled:false}]},bgm_sfx_saved:true},progress_payload:{bgm_sfx_saved:true}};
test('reviewed project accepts scoped SFX deletion and replacement',()=>assert.equal(exports_.canEditStdProject('review_requested',body),true));
test('audio scope cannot edit narration, scenes, review decisions, or final projects',()=>{for(const altered of [{...body,project_payload:{...body.project_payload,subtitles:[]}},{...body,title:'changed'},{...body,progress_payload:{approved:true}}])assert.equal(exports_.canEditStdProject('review_requested',altered),false);for(const status of ['approved','canceled'])assert.equal(exports_.canEditStdProject(status,body),false)})

test('final subtitle save with subtitle scope passes review policy before TTS',()=>{
 const save={render_settings_scope:'subtitle',project_payload:{subtitles:[{id:'s',scene_number:10,text:'復元'}],subtitles_saved:true,render_settings:{subtitle_font_size:5.4}},progress_payload:{subtitles_saved:true,subtitles_completed:true}}
 assert.equal(exports_.canEditStdProject('review_requested',save),true)
 assert.equal(exports_.canEditStdProject('review_requested',{...save,render_settings_scope:'unknown'}),false)
 assert.equal(exports_.canEditStdProject('review_requested',{...save,allow_scene_update:true}),false)
 assert.equal(exports_.canEditStdProject('approved',save),false)
 assert.equal(exports_.canEditStdProject('canceled',save),false)
})
