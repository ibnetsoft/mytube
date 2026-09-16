const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const page = fs.readFileSync(require.resolve('../app/std/page.tsx'), 'utf8')
function compile(start, end, name, context) {
    const src = page.slice(page.indexOf(start), page.indexOf(end, page.indexOf(start)))
    return new Function(...Object.keys(context), ts.transpile(src + `\nreturn ${name}`, {target: ts.ScriptTarget.ES2020}))(...Object.values(context))
}
async function main() {
    const directStorageUrl = a => a?.metadata?.storage_public_url || ''
    const asset = {id:'a', asset_type:'audio', status:'uploaded', metadata:{upload_mode:'server_supabase_storage', storage_public_url:'https://storage.example/audio.mp3'}}
    let fetched
    const context = {selectedProject:{project:{id:'p'},assets:[asset]},localSubtitles:[{voice_id:'studio'}],isVoiceStudioVoice:()=>false,
        directStorageUrl,vrewFinalNarrationAudioRef:{current:null},URL:{revokeObjectURL:()=>{}},fetchVrewAudioBlobUrl:async url => {fetched=url;return 'blob:audio'}}
    const getAudio = compile('    const getSavedNarrationAudioUrl =','    const getOrCreateVrewSegmentAudioUrl','getSavedNarrationAudioUrl',context)
    assert.equal(await getAudio(),'https://storage.example/audio.mp3')
    assert.equal(fetched,undefined,'Storage upload must not depend on Drive or new TTS')
    delete asset.metadata.storage_public_url
    assert.equal(await getAudio(),'blob:audio')
    assert.match(fetched,/assets\/file\?assetId=a/)
    const studioAudio = compile('    const getSavedNarrationAudioUrl =','    const getOrCreateVrewSegmentAudioUrl','getSavedNarrationAudioUrl', {...context,isVoiceStudioVoice:()=>true})
    assert.equal(await studioAudio(),null,'Voice Studio narration must not be replaced by uploaded music')
    let backgroundUpload
    const upload = compile('    const handleUploadExternalAudio =','    const assetPlaybackUrl','handleUploadExternalAudio',{
        handleUploadBgmFile:async event=>{backgroundUpload=event},
    })
    const event={target:{files:[{name:'music.mp3'}]}}
    await upload(event)
    assert.equal(backgroundUpload,event,'Audio button must use background upload, not replace narration')
    const calls=[]
    const uploadDirect = compile('    const uploadDriveAudioAsset =','    const handleUploadBgmFile','uploadDriveAudioAsset',{
        selectedProject:context.selectedProject,authedJsonHeaders:{Authorization:'test'},safeParseJson:async r=>r.data,
        fetch:async(url,options)=>{calls.push({url,...options});if(url.endsWith('/init'))return {ok:true,data:{storage_upload_url:'https://storage.example/upload',storage_path:'p/file'}};
            if(url.endsWith('/complete'))return {ok:true,data:{asset}};return {ok:true}},
    })
    const file={name:'large.mp3',type:'audio/mpeg',size:9000000}
    assert.equal(await uploadDirect(file,'bgm'),asset)
    assert.equal(calls[1].method,'PUT');assert.equal(calls[1].body,file)
    assert.equal(calls[0].body.includes('bgm'),true)
    assert.equal(calls[2].body.includes('p/file'),true)
    let played = false
    const bgm = {duration:30,readyState:1,currentTime:0,volume:1,play:()=>{played=true;return Promise.resolve()}}
    const playBgm = compile('    const playPreviewBgm =','    const stopVrewPlayback','playPreviewBgm',{
        previewBgmAudioRef:{current:bgm},bgmVolume:0.08,backgroundVolume:v=>v,HTMLMediaElement:{HAVE_METADATA:1},setMessage:()=>{},
    })
    playBgm(65)
    assert.equal(played,true);assert.equal(bgm.currentTime,5);assert.equal(bgm.volume,0.08)
    console.log('PASS: Narration preserved, music routed to BGM, default background gain 8%, authenticated fallback and direct upload')
}
main().catch(e=>{console.error(e);process.exitCode=1})
