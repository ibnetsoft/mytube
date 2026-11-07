const test = require('node:test'), assert = require('node:assert/strict'), path = require('node:path'), fs = require('node:fs'), ts = require('typescript')
const load = require('./load-ts.cjs')
const { stdProjectListDisplay, projectListThumbnailUrl, projectListThumbnailCandidates, advanceProjectListThumbnail, listedProjectStepStatus } = load(path.join(__dirname, '../lib/stdProjectListDisplay.ts'))
const summaryExports = {}
new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdProjectStepStatus.ts'), 'utf8'), { compilerOptions: { module: 1, target: 9 } }).outputText)(summaryExports,
    name => name === './stdNonverbal' ? { hasReadyNonverbalPlan: () => false } : { savedStdOutputStepStatus: () => ({}) })
const { summarizeStdProject } = summaryExports

test('stored versions survive status projection; submission history never invents v1', () => {
    for (const version of [3, 11, 9, 2]) assert.equal(stdProjectListDisplay({ saved_render_version: version }).latest_render_version, version)
    assert.equal(stdProjectListDisplay({ submitted_at: '2026-10-21', shared_submission: { submitted_at: '2026-10-20' } }).latest_render_version, null)
    for (const version of ['bad', -1, 0, 2.5]) assert.equal(stdProjectListDisplay({ saved_render_version: version }).latest_render_version, null)
})

test('saved final thumbnails take priority over worker backgrounds; temporary URLs are ignored', () => {
    const asset = { id: 'thumb', asset_type: 'thumbnail', status: 'uploaded', metadata: { gcs_path: 'final.png' } }
    assert.equal(stdProjectListDisplay({ id: 'p' }, { project_payload: { thumbnail_url: '/saved-final.png' } }, [asset]).thumbnail_url, '/saved-final.png')
    assert.equal(stdProjectListDisplay({ id: 'p', saved_thumbnail_design_url: '/design-final.png' }, {}, [asset]).thumbnail_url, '/design-final.png')
    assert.equal(stdProjectListDisplay({ id: 'p' }, { project_payload: { thumbnail_url: 'blob:old', thumbnail_design: { bg_url: '/background.png' } } }, [asset]).thumbnail_url, '/api/std/projects/p/assets/file?assetId=thumb')
    assert.equal(stdProjectListDisplay({ id: 'p' }, { project_payload: { thumbnail_design: { bg_url: '/background.png' } } }).thumbnail_url, '/background.png')
})

test('administrator thumbnail proxies include the viewed owner without leaking it to external storage', () => {
    const proxy = projectListThumbnailUrl('/api/std/projects/p/assets/file?assetId=a', 'owner@example.test')
    assert.equal(new URL(proxy, 'https://studio.test').searchParams.get('impersonate'), 'owner@example.test')
    assert.equal(projectListThumbnailUrl('https://storage.test/final.png', 'owner@example.test'), 'https://storage.test/final.png')
    assert.equal(projectListThumbnailUrl('blob:stale'), '')
    assert.equal(new URL(projectListThumbnailUrl('/api/std/assets/gcs-file?bucket=test&path=image.png'),'https://test').searchParams.get('preview'),'960')
})

test('missing saved status never borrows completion from an editor or submitted timestamp', () => {
    assert.equal(listedProjectStepStatus({ submitted_at: 'today', project_payload: { script: 'draft' } }).allDone, false)
    assert.equal(summarizeStdProject({ title: 'Saved', project_payload: { scenes: [], structure: { scenes: [{ scene_number: 1, scene_text: 'Saved narration' }] } } }).isScriptDone, true)
})

const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
const marker = page.indexOf('        if (!topicProjectOpen || !token) return')
const start = page.lastIndexOf('    useEffect(() => {', marker)
const end = page.indexOf('    useEffect(() => {', marker)
const effect = ts.transpileModule(page.slice(start, end), { compilerOptions: { target: 9 } }).outputText
const flush = () => new Promise(resolve => setImmediate(resolve))
function refresh() {
    const events = [], headers = { Authorization: 'Bearer test', 'x-impersonate-email': 'owner@example.test' }
    let respond, cleanup
    const fetch = async (url, options) => { assert.equal(url, '/api/std/projects'); assert.equal(options.headers, headers); assert.equal(options.cache, 'no-store'); return new Promise(resolve => { respond = resolve }) }
    const context = { useEffect: callback => { cleanup = callback() }, topicProjectOpen: true, token: 'test', authedJsonHeaders: headers, projectsRefreshKey: 0,
        window: { setTimeout: () => 1, clearTimeout() {} }, AbortController, fetch,
        projectListScopeRef:{current:'owner'},projectListGenerationRef:{current:0},forceProjectListRefreshRef:{current:false},
        fetchSharedProjectList:(url,headers)=>fetch(url,{headers,cache:'no-store'}), acceptProjectList:value=>events.push(['rows',value]), setProjects: value => events.push(['rows', value]), setProjectsRefreshing: value => events.push(['loading', value]), setProjectsLoadError: value => events.push(['error', value]) }
    new Function(...Object.keys(context), effect)(...Object.values(context))
    return { events, respond: value => respond(value), cleanup: () => cleanup() }
}

test('list opening reloads persisted state and rejects malformed responses', async () => {
    const success = refresh()
    success.respond(Response.json({ success: true, projects: [{ id: 'saved', step_status: { allDone: false } }] }))
    await flush(); await flush()
    assert.deepEqual(success.events.find(event => event[0] === 'rows')[1], [{ id: 'saved', step_status: { allDone: false } }])
    for (const body of [{ success: false, projects: [] }, { success: true }, { error: 'offline' }]) {
        const failure = refresh(); failure.respond(Response.json(body)); await flush(); await flush()
        assert.equal(failure.events.some(event => event[0] === 'rows'), false)
        assert(failure.events.some(event => event[0] === 'error' && event[1]))
    }
})

test('closed or switched account requests cannot overwrite the next list', async () => {
    const stale = refresh(); stale.cleanup()
    stale.respond(Response.json({ success: true, projects: [{ id: 'previous-owner' }] }))
    await flush(); await flush()
    assert.equal(stale.events.some(event => event[0] === 'rows'), false)
})

test('worker draft and current scene previews fill empty thumbnails without completing the thumbnail step',()=>{
 const draft=stdProjectListDisplay({id:'p',saved_thumbnail_bg_url:'/api/std/draft.png'})
 assert.equal(draft.thumbnail_url,'/api/std/draft.png')
 assert.equal(listedProjectStepStatus(draft).isThumbnailDone,false)
 assert.equal(stdProjectListDisplay({id:'p'},{project_payload:{scenes:[{image_url:'/api/std/scene1.png'}]}}).thumbnail_url,'/api/std/scene1.png')
 const full=stdProjectListDisplay({id:'p',saved_thumbnail_bg_url:'/api/std/draft.png'},{project_payload:{thumbnail_url:'/api/std/final.png',scenes:[{image_url:'/api/std/scene1.png'}]}})
 const candidates=projectListThumbnailCandidates(full,'owner@test')
 assert.deepEqual(candidates.map(x=>new URL(x,'https://test').pathname),['/api/std/final.png','/api/std/draft.png','/api/std/scene1.png'])
 assert(candidates.every(x=>new URL(x,'https://test').searchParams.get('impersonate')==='owner@test'))
 const img={dataset:{},src:candidates[0],hidden:false}
 advanceProjectListThumbnail(img,candidates);assert.equal(img.src,candidates[1])
 advanceProjectListThumbnail(img,candidates);assert.equal(img.src,candidates[2])
 advanceProjectListThumbnail(img,candidates);assert.equal(img.hidden,true)
})
