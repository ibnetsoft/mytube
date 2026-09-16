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
    const context = {selectedProject:{project:{id:'p'},assets:[asset]},localSubtitles:[{voice_id:'studio'}],isVoiceStudioVoice:()=>true,
        directStorageUrl,vrewFinalNarrationAudioRef:{current:null},URL:{revokeObjectURL:()=>{}},fetchVrewAudioBlobUrl:async url => {fetched=url;return 'blob:audio'}}
    const getAudio = compile('    const getSavedNarrationAudioUrl =','    const getOrCreateVrewSegmentAudioUrl','getSavedNarrationAudioUrl',context)
    assert.equal(await getAudio(),'https://storage.example/audio.mp3')
    assert.equal(fetched,undefined,'Storage upload must not depend on Drive or new TTS')
    delete asset.metadata.storage_public_url
    assert.equal(await getAudio(),'blob:audio')
    assert.match(fetched,/assets\/file\?assetId=a/)
    let messages=[],audioUrl='',project=context.selectedProject,fail=true
    const upload = compile('    const handleUploadExternalAudio =','    const assetPlaybackUrl','handleUploadExternalAudio',{
        selectedProject:project,uploadDriveAudioAsset:async()=>{if(fail)throw Error('upload failed');return asset},directStorageUrl,
        assetPlaybackUrl:()=>'/assets/file?assetId=a',setAudioResultUrl:u=>audioUrl=u,setUploadingKey:()=>{},
        setSelectedProject:fn=>project=fn(project),rememberProjectState:()=>{},setMessage:m=>messages.push(m),
    })
    await upload({target:{files:[{name:'test.mp3'}],value:'test'}})
    assert.deepEqual(messages,['upload failed']);assert.equal(audioUrl,'')
    fail=false;messages=[]
    await upload({target:{files:[{name:'test.mp3'}],value:'test'}})
    assert.equal(audioUrl,'/assets/file?assetId=a');assert.equal(project.assets[0].id,'a')
    assert.match(messages[0],/미리보기에 적용/)
    const calls=[]
    const uploadDirect = compile('    const uploadDriveAudioAsset =','    const handleUploadBgmFile','uploadDriveAudioAsset',{
        selectedProject:project,authedJsonHeaders:{Authorization:'test'},safeParseJson:async r=>r.data,
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
        previewBgmAudioRef:{current:bgm},bgmSfxSettings:{bgm_volume:0.25},HTMLMediaElement:{HAVE_METADATA:1},setMessage:()=>{},
    })
    playBgm(65)
    assert.equal(played,true);assert.equal(bgm.currentTime,5);assert.equal(bgm.volume,0.25)
    console.log('PASS: Storage audio overrides generated voices, authenticated fallback, no false upload success, direct large-file upload')
}
main().catch(e=>{console.error(e);process.exitCode=1})
