const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript')
const exportsObject={};new Function('exports',ts.transpileModule(fs.readFileSync(path.join(__dirname,'../lib/stdMouthPreview.ts'),'utf8'),{compilerOptions:{module:1,target:7}}).outputText)(exportsObject)
const {subtitleMouthPreview}=exportsObject
test('saved preview appears only as display media and never replaces final source video',()=>{
 const scene={video_url:null,mouth_preview_url:'/preview.mp4',mouth_preview:{state:'ready',voice_synced:false,preserve_original:false}}
 const saved=JSON.stringify(scene),view=subtitleMouthPreview(scene,scene.video_url)
 assert.equal(view.url,'/preview.mp4');assert.match(view.label,/3초.*음성 싱크 전/)
 assert.equal(JSON.stringify(scene),saved)
 const final=subtitleMouthPreview(scene,'/final-dialogue.mp4')
 assert.equal(final.url,'/final-dialogue.mp4');assert.equal(final.isMouthPreview,false);assert.equal(final.label,'')
})
test('reopened geometry and preserved-mouth clips retain their accurate status',()=>{
 const scene={metadata:{cowork_image_asset:{speaker_geometry:{mouth_preview:{state:'ready',url:'/preserved.mp4',preserve_original:true}}}}}
 assert.equal(subtitleMouthPreview(scene).url,'/preserved.mp4')
 assert.match(subtitleMouthPreview(scene).label,/3초.*원본 유지/)
 assert.equal(subtitleMouthPreview({mouth_preview_url:'/stale.mp4',mouth_preview:{state:'failed'}}).url,'')
})
