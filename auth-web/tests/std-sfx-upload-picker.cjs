const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const test = require('node:test')
const page = fs.readFileSync('auth-web/app/std/page.tsx', 'utf8')
const start = page.indexOf('    const uploadSelectableSfx =')
const end = page.indexOf('    const clearBgmSetting', start)
test('completed upload adds selectable SFX to latest assets before opening its picker', async () => {
    const selectedProject = {project:{id:'p'},assets:[{id:'old'}]}
    let state = {...selectedProject,assets:[{id:'concurrent'}]}, selected, tab, request, message
    const asset = {id:'knock',file_name:'knock.mp3',asset_type:'other',metadata:{audio_role:'sfx'},status:'uploaded'}
    const context = {selectedProject, uploadDriveAudioAsset:async()=>asset, setUploadingKey:()=>{},
        setSelectedProject:fn=>{state=fn(state)},rememberProjectState:()=>{},setSelectedSfxAssetId:v=>selected=v,
        setSubEditTab:v=>tab=v,setSfxPickerOpenRequest:v=>request=v,setMessage:v=>message=v}
    const compiled = ts.transpileModule(page.slice(start,end)+'\nreturn handleUploadCurrentSfxFile', {compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText
    const upload = new Function(...Object.keys(context),compiled)(...Object.values(context))
    await upload({target:{files:[{name:'knock.mp3'}],value:'file'}})
    assert.deepEqual(state.assets.map(a=>a.id),['knock','concurrent'])
    assert.equal(selected,'knock'); assert.equal(tab,'bgm'); assert.ok(request>0)
    assert.match(message,/팝업/)
})
