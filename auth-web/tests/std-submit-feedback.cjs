const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const noticeExports = {}
new Function('exports', 'require', ts.transpileModule(
    fs.readFileSync(path.resolve(__dirname, '../components/StdSubmissionNotice.tsx'), 'utf8'), {
        compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText)(noticeExports, id => {
    if (id === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) }
    if (id === 'lucide-react') return { AlertCircle: 'alert-icon', CheckCircle2: 'success-icon', RefreshCw: 'spinner', X: 'close-icon' }
    throw Error(`Unexpected dependency: ${id}`)
})
const { default: StdSubmissionNotice, submissionNoticeCopy } = noticeExports
const scopeExports = {}
new Function('exports', ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../lib/stdMediaScope.ts'), 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText)(scopeExports)
const { isCurrentMediaScope } = scopeExports

const page = fs.readFileSync(path.resolve(__dirname, '../app/std/page.tsx'), 'utf8')
const start = page.indexOf('    const submitProject =')
const end = page.indexOf('    const handleStartRender =', start)
assert.ok(start >= 0 && end > start, 'Submit handler must remain discoverable')
const submitSource = ts.transpileModule(`${page.slice(start, end)}\nreturn submitProject`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText
const acceptedStart = page.indexOf('    const notifyRenderAccepted =')
const acceptedEnd = page.indexOf('    // 1.1 언어', acceptedStart)
assert.ok(acceptedStart >= 0 && acceptedEnd > acceptedStart)
const acceptedSource = ts.transpileModule(`${page.slice(acceptedStart, acceptedEnd)}\nreturn notifyRenderAccepted`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

function deferred() {
    let resolve, reject
    const promise = new Promise((yes, no) => { resolve = yes; reject = no })
    return { promise, resolve, reject }
}

function harness(options = {}) {
    const selectedProject = {
        project: { id: 'project-a', title: 'Project A', status: 'in_progress', project_payload: {}, progress_payload: {} },
        scenes: [], assets: [],
    }
    const initialProjects = [selectedProject.project, { id: 'project-b', title: 'Project B', status: 'in_progress' }]
    const state = {
        notices: [], busy: [], messages: [], accepted: [], requests: [], alerts: [], confirmations: [],
        syncs: 0, saves: [], reloads: [], opens: [], projects: initialProjects, project: selectedProject, projectUpdates: [], timeouts: [], operations: [],
    }
    const submittingProjectRef = { current: '' }
    const mediaScopeRef = { current: { session: 'session-a', projectId: 'project-a', generation: 1 } }
    const reportAccepted = new Function('setRenderSubmissionNotice', acceptedSource)(notice => state.notices.push(notice))
    const context = {
        selectedProject, projects: initialProjects, token: 'fixture-token', currentLocale: 'ko', submissionNoticeCopy,
        submittingProjectId: '', submittingProjectRef, mediaScopeRef, isCurrentMediaScope,
        subtitleSaveState: options.saveState || 'saved',
        subtitleTextSaveTimerRef: { current: options.pendingText ? 123 : null },
        subtitleStyleSaveTimerRef: { current: options.pendingStyle ? 456 : null },
        getProjectSyncedTitle: project => project?.project?.title || '',
        setSubmittingProjectId: value => state.busy.push(value),
        setLoading() {},
        setRenderSubmissionNotice: notice => state.notices.push(notice),
        setMessage: value => state.messages.push(value),
        notifyRenderAccepted: (...args) => { state.accepted.push(args); reportAccepted(...args) },
        setProjects: update => {
            state.projects = typeof update === 'function' ? update(state.projects) : update
            state.projectUpdates.push(state.projects)
        },
        setSelectedProject: update => { state.project = typeof update === 'function' ? update(state.project) : update },
        alert: message => state.alerts.push(message),
        confirm: message => { state.confirmations.push(message); return options.confirm !== false },
        ensureScriptSyncedBeforeAction: async () => {
            state.syncs++
            state.operations.push('sync')
            if (options.syncGate) await options.syncGate.promise
            if (options.syncError) throw Error(options.syncError)
            return options.sync !== false
        },
        handleSaveSubtitles: async (...args) => {
            state.saves.push(args)
            state.operations.push('save')
            if (options.saveGate) await options.saveGate.promise
            if (options.saveError) throw Error(options.saveError)
            if (options.save === false) return false
        },
        authedJsonHeaders: { Authorization: 'Bearer fixture-token' },
        AbortSignal: { timeout: milliseconds => { state.timeouts.push(milliseconds); return { deadline: milliseconds } } },
        safeParseJson: async response => response.payload,
        fetch: async (url, init) => {
            if (url === '/api/std/projects') {
                state.reloads.push({ url, init })
                if (options.reloadGate) await options.reloadGate.promise
                if (options.reloadError) throw Error(options.reloadError)
                return { ok: true, status: 200, payload: { success: true, projects: state.projects } }
            }
            state.requests.push({ url, init })
            state.operations.push('post')
            if (options.requestGate) await options.requestGate.promise
            if (options.requestError) {
                const error = Error(options.requestError)
                if (options.errorName) error.name = options.errorName
                throw error
            }
            return {
                ok: options.status === undefined || options.status < 400,
                status: options.status || 200,
                payload: options.payload || { success: true, render_version: 2 },
            }
        },
        loadStdData: async (...args) => {
            throw Error('Submission must not load editor data')
        },
        openProject: async (...args) => { state.opens.push(args); throw Error('Submission must not reopen the project') },
        console: { warn() {}, error() {} },
    }
    const submitProject = new Function(...Object.keys(context), submitSource)(...Object.values(context))
    return { state, submitProject, submittingProjectRef, mediaScopeRef, options }
}

const phases = h => h.state.notices.filter(Boolean).map(notice => notice.phase)

test('click immediately locks submission and shows progress before asynchronous draft work', async () => {
    const syncGate = deferred(), h = harness({ syncGate })
    const running = h.submitProject()
    assert.equal(h.submittingProjectRef.current, 'project-a')
    assert.equal(h.state.busy.at(-1), 'project-a')
    assert.equal(h.state.notices[0]?.phase, 'running')
    assert.equal(h.state.notices[0]?.projectId, 'project-a')
    assert.equal(h.state.requests.length, 0)
    await h.submitProject()
    await h.submitProject('project-b')
    assert.equal(h.state.confirmations.length, 1)
    assert.equal(h.state.syncs, 1)
    syncGate.resolve()
    await running
    assert.equal(h.state.requests.length, 1)
    assert.equal(h.submittingProjectRef.current, '')
    assert.equal(h.state.busy.at(-1), '')
})

test('project list submits the requested ID directly without loading its editor or saving another project', async () => {
    const h = harness({ saveState: 'dirty' })
    await h.submitProject('project-b')
    assert.equal(h.state.requests[0].url, '/api/std/projects/project-b/submit')
    assert.equal(h.state.requests[0].init.method, 'POST')
    assert.equal(h.state.syncs, 0)
    assert.equal(h.state.saves.length, 0)
    assert.equal(h.state.opens.length, 0)
    assert.equal(h.state.notices[0].title, 'Project B')
    assert.equal(h.state.accepted[0][0], 'project-b')
    assert.deepEqual(h.state.timeouts, [180000, 15000])
    assert.equal(h.state.requests[0].init.signal.deadline, 180000)
})

test('cancelling confirmation does not start a request or mutate busy state', async () => {
    const h = harness({ confirm: false })
    await h.submitProject()
    assert.equal(h.state.confirmations.length, 1)
    assert.equal(h.state.requests.length, 0)
    assert.equal(h.state.syncs, 0)
    assert.equal(h.state.busy.length, 0)
    assert.equal(h.state.notices.length, 0)
    assert.equal(h.submittingProjectRef.current, '')
})

test('dirty, saving, failed, and queued subtitle edits are persisted before submission', async () => {
    for (const options of [{ saveState: 'dirty' }, { saveState: 'saving' }, { saveState: 'error' }, { pendingText: true }, { pendingStyle: true }]) {
        const saveGate = deferred(), h = harness({ ...options, saveGate })
        const running = h.submitProject()
        await Promise.resolve()
        assert.deepEqual(h.state.saves, [[false]])
        assert.equal(h.state.requests.length, 0)
        saveGate.resolve()
        await running
        assert.equal(h.state.requests.length, 1)
        assert.equal(h.state.accepted.length, 1)
        assert.deepEqual(h.state.operations, ['save', 'sync', 'post'])
    }
})

test('subtitle or script save failures stop submission and give visible retryable failure', async () => {
    for (const options of [{ saveState: 'dirty', saveError: 'Draft save failed' }, { saveState: 'dirty', save: false }, { sync: false }, { syncError: 'Script save failed' }]) {
        const h = harness(options)
        await h.submitProject()
        assert.equal(h.state.requests.length, 0)
        assert.equal(h.state.accepted.length, 0)
        assert.equal(phases(h).at(-1), 'error')
        assert.equal(h.submittingProjectRef.current, '')
        assert.equal(h.state.busy.at(-1), '')
    }
})

test('HTTP failure and unsuccessful or malformed 200 replies never claim queue acceptance', async () => {
    for (const options of [
        { status: 500, payload: { error: 'GCS unavailable' } },
        { payload: { success: false, error: 'Missing scenes', missing_scene_numbers: [24] } },
        { payload: {} },
        { requestError: 'Request timed out' },
    ]) {
        const h = harness(options)
        await h.submitProject('project-b')
        assert.equal(phases(h).at(-1), 'error')
        assert.equal(h.state.accepted.length, 0)
        assert.equal(h.state.reloads.length, 0)
        assert.equal(h.state.projectUpdates.length, 0)
        assert.equal(h.submittingProjectRef.current, '')
        assert.equal(h.state.busy.at(-1), '')
    }
})

test('failed submissions can be retried after the lock is released', async () => {
    const options = { status: 500, payload: { success: false, error: 'Temporary outage' } }, h = harness(options)
    await h.submitProject('project-b')
    options.status = 200
    options.payload = { success: true, render_version: 3 }
    await h.submitProject('project-b')
    assert.equal(h.state.requests.length, 2)
    assert.equal(h.state.accepted.length, 1)
    assert.equal(h.state.projectUpdates.length, 2)
    assert.equal(h.submittingProjectRef.current, '')
})

test('server acceptance updates the matching list row and never reopens the editor', async () => {
    for (const extra of [{}, { already_submitted: true }, { shared_submission: true }]) {
        const h = harness({ payload: { success: true, render_version: 2, ...extra } })
        await h.submitProject('project-b')
        assert.equal(h.state.accepted.length, 1)
        assert.equal(h.state.projects[0].status, 'in_progress')
        assert.equal(h.state.projects[1].status, 'review_requested')
        assert.ok(h.state.projects[1].submitted_at)
        assert.equal(h.state.reloads.length, 1)
        assert.equal(h.state.reloads[0].url, '/api/std/projects')
        assert.equal(h.state.reloads[0].init.signal.deadline, 15000)
        assert.equal(h.state.opens.length, 0)
        assert.equal(phases(h).at(-1), 'success')
    }
})

test('a list refresh failure after queue acceptance warns without claiming submission failure', async () => {
    const h = harness({ reloadError: 'List refresh failed' })
    await h.submitProject('project-b')
    assert.equal(h.state.accepted.length, 1)
    assert.equal(h.state.projects[1].status, 'review_requested')
    assert.equal(phases(h).at(-1), 'warning')
    assert.ok(!phases(h).includes('error'))
    assert.equal(h.state.alerts.length, 0)
    assert.equal(h.state.opens.length, 0)
    assert.equal(h.submittingProjectRef.current, '')
})

test('a changed login session receives no old completion notice, list update, or refresh', async () => {
    const requestGate = deferred(), h = harness({ requestGate })
    const running = h.submitProject('project-b')
    assert.equal(h.state.requests.length, 1)
    h.mediaScopeRef.current = { session: 'session-b', projectId: 'project-c', generation: 2 }
    requestGate.resolve()
    await running
    assert.equal(h.state.accepted.length, 0)
    assert.equal(h.state.projectUpdates.length, 0)
    assert.equal(h.state.reloads.length, 0)
    assert.ok(phases(h).every(phase => phase === 'running'))
    assert.equal(h.submittingProjectRef.current, '')
})

test('an interrupted POST reports uncertain status so the user checks the queue before retrying', async () => {
    for (const errorName of ['TimeoutError', 'AbortError']) {
        const h = harness({ requestError: 'Request interrupted', errorName })
        await h.submitProject('project-b')
        assert.equal(phases(h).at(-1), 'warning')
        assert.equal(h.state.notices.at(-1).detail, submissionNoticeCopy('ko').timeout)
        assert.equal(h.state.accepted.length, 0)
        assert.equal(h.state.reloads.length, 0)
        assert.equal(h.submittingProjectRef.current, '')
    }
})

test('a login change during the list refresh does not overwrite the new session list', async () => {
    const reloadGate = deferred(), h = harness({ reloadGate })
    const running = h.submitProject('project-b')
    for (let i = 0; i < 5 && !h.state.reloads.length; i++) await Promise.resolve()
    assert.equal(h.state.reloads.length, 1)
    assert.equal(h.state.projectUpdates.length, 1)
    h.mediaScopeRef.current = { session: 'session-b', projectId: 'project-c', generation: 2 }
    h.state.projects = [{ id: 'project-c', title: 'New session project' }]
    reloadGate.resolve()
    await running
    assert.deepEqual(h.state.projects, [{ id: 'project-c', title: 'New session project' }])
    assert.equal(h.state.projectUpdates.length, 1)
})

test('project or login changes while saving a draft prevent submitting stale editor data', async () => {
    for (const sessionChange of [false, true]) {
        const saveGate = deferred(), h = harness({ saveGate, saveState: 'dirty' })
        const running = h.submitProject()
        assert.equal(h.state.saves.length, 1)
        h.mediaScopeRef.current = { session: sessionChange ? 'session-b' : 'session-a', projectId: 'project-b', generation: 2 }
        saveGate.resolve()
        await running
        assert.equal(h.state.requests.length, 0)
        assert.equal(h.state.accepted.length, 0)
        assert.equal(h.submittingProjectRef.current, '')
        assert.equal(phases(h).at(-1), sessionChange ? 'running' : 'error')
    }
})

const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value)
    ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)]
test('submission notices are accessible, localized, and keep failures visible until dismissed', () => {
    assert.equal(StdSubmissionNotice({ notice: null, locale: 'ko', onDismiss() {} }), null)
    for (const locale of ['ko', 'th', 'en', 'vi']) {
        for (const phase of ['running', 'success', 'warning', 'error']) {
            let dismissed = 0
            const copy = submissionNoticeCopy(locale)
            const tree = nodes(StdSubmissionNotice({ notice: { projectId: 'project-a', title: 'Project A', phase, detail: copy.preparing }, locale, onDismiss: () => { dismissed++ } }))
            const region = tree.find(node => node.type === 'section')
            assert.equal(region.props['aria-label'], copy[phase])
            assert.ok(tree.some(node => node.props.role === (phase === 'error' ? 'alert' : 'status')))
            const buttons = tree.filter(node => node.type === 'button')
            if (phase === 'running') {
                assert.equal(buttons.length, 0)
                assert.ok(tree.some(node => node.props.children === copy.navigation))
            } else {
                assert.ok(buttons.length > 0)
                buttons[0].props.onClick()
                assert.equal(dismissed, 1)
            }
        }
    }
})
