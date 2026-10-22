const test = require('node:test'), assert = require('node:assert/strict'), path = require('node:path'), fs = require('node:fs'), ts = require('typescript')
const load = require('./load-ts.cjs')
const { stdProjectListDisplay, projectListThumbnailUrl, listedProjectStepStatus } = load(path.join(__dirname, '../lib/stdProjectListDisplay.ts'))
const summaryExports = {}
new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdProjectStepStatus.ts'), 'utf8'), { compilerOptions: { module: 1, target: 9 } }).outputText)(summaryExports,
    name => name === './stdNonverbal' ? { hasReadyNonverbalPlan: () => false } : { savedStdOutputStepStatus: () => ({}) })
const { summarizeStdProject } = summaryExports

test('stored versions survive status projection; submission history never invents v1', () => {
    for (const version of [3, 11, 9, 2]) assert.equal(stdProjectListDisplay({ saved_render_version: version }).latest_render_version, version)
    assert.equal(stdProjectListDisplay({ submitted_at: '2026-10-21', shared_submission: { submitted_at: '2026-10-20' } }).latest_render_version, null)
    for (const version of ['bad', -1, 0, 2.5]) assert.equal(stdProjectListDisplay({ saved_render_version: version }).latest_render_version, null)
})

test('saved final thumbnails take priority and background or temporary previews cannot replace them', () => {
    const asset = { id: 'thumb', asset_type: 'thumbnail', status: 'uploaded', metadata: { gcs_path: 'final.png' } }
    assert.equal(stdProjectListDisplay({ id: 'p' }, { project_payload: { thumbnail_url: '/saved-final.png' } }, [asset]).thumbnail_url, '/saved-final.png')
    assert.equal(stdProjectListDisplay({ id: 'p', saved_thumbnail_design_url: '/design-final.png' }, {}, [asset]).thumbnail_url, '/design-final.png')
    assert.equal(stdProjectListDisplay({ id: 'p' }, { project_payload: { thumbnail_url: 'blob:old', thumbnail_design: { bg_url: '/background.png' } } }, [asset]).thumbnail_url, '/api/std/projects/p/assets/file?assetId=thumb')
    assert.equal(stdProjectListDisplay({ id: 'p' }, { project_payload: { thumbnail_design: { bg_url: '/background.png' } } }).thumbnail_url, '')
})

test('administrator thumbnail proxies include the viewed owner without leaking it to external storage', () => {
    const proxy = projectListThumbnailUrl('/api/std/projects/p/assets/file?assetId=a', 'owner@example.test')
    assert.equal(new URL(proxy, 'https://studio.test').searchParams.get('impersonate'), 'owner@example.test')
    assert.equal(projectListThumbnailUrl('https://storage.test/final.png', 'owner@example.test'), 'https://storage.test/final.png')
    assert.equal(projectListThumbnailUrl('blob:stale'), '')
})

test('missing saved status never borrows completion from an editor or submitted timestamp', () => {
    assert.equal(listedProjectStepStatus({ submitted_at: 'today', project_payload: { script: 'draft' } }).allDone, false)
    assert.equal(summarizeStdProject({ title: 'Saved', project_payload: { scenes: [], structure: { scenes: [{ scene_number: 1, scene_text: 'Saved narration' }] } } }).isScriptDone, true)
})

const page = fs.readFileSync(path.join(__dirname, '../app/std/page.tsx'), 'utf8')
const marker = page.indexOf('        if (!topicProjectOpen || !token) return')
const start = page.lastIndexOf('    useEffect(() => {', marker)
const end = page.indexOf('    const openProjectList =', start)
const effect = ts.transpileModule(page.slice(start, end), { compilerOptions: { target: 9 } }).outputText
const flush = () => new Promise(resolve => setImmediate(resolve))
function refresh() {
    const events = [], headers = { Authorization: 'Bearer test', 'x-impersonate-email': 'owner@example.test' }
    let respond, cleanup
    const fetch = async (url, options) => { assert.equal(url, '/api/std/projects'); assert.equal(options.headers, headers); assert.equal(options.cache, 'no-store'); return new Promise(resolve => { respond = resolve }) }
    const context = { useEffect: callback => { cleanup = callback() }, topicProjectOpen: true, token: 'test', authedJsonHeaders: headers, projectsRefreshKey: 0,
        window: { setTimeout: () => 1, clearTimeout() {} }, AbortController, fetch,
        setProjects: value => events.push(['rows', value]), setProjectsRefreshing: value => events.push(['loading', value]), setProjectsLoadError: value => events.push(['error', value]) }
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
