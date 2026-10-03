const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

// Exercise the real lookup and POST boundary; synthesis is a spy so failures
// cannot accidentally make a provider call (or spend money) during this test.
const route = fs.readFileSync(path.join(__dirname, '../app/api/std/projects/[projectId]/tts/generate/route.ts'), 'utf8')
const from = route.indexOf('function topicIdFromProjectParam(')
const to = route.indexOf('async function runTts(', from)
assert(from >= 0 && to > from, 'Missing TTS lookup/POST source')
const compiled = ts.transpileModule(route.slice(from, to), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

const projectId = 'e9233112-f0d7-4b35-91bf-2f892844eb30'
const ownerEmail = 'owner@example.test'
const project = { id: projectId, employee_email: ownerEmail, project_payload: {} }
const ok = data => ({ data, error: null, status: 200 })
const failed = (message, status = 500, code = '') => ({ data: null, error: { message, code }, status })

function harness(replies) {
    const calls = [], providerCalls = [], exports = {}
    let responseIndex = 0
    const supabaseAdmin = {
        from(table) {
            const record = { table, operation: 'read', filters: [], payload: null }
            let executed
            const execute = () => {
                if (!executed) executed = Promise.resolve().then(() => {
                    calls.push({ ...record, filters: record.filters.slice() })
                    assert(responseIndex < replies.length, `Unexpected database call: ${JSON.stringify(record)}`)
                    const reply = replies[responseIndex++]
                    if (reply instanceof Error) throw reply
                    return typeof reply === 'function' ? reply(record) : reply
                })
                return executed
            }
            const query = {
                select() { return query },
                eq(key, value) { record.filters.push([key, value]); return query },
                insert(payload) { record.operation = 'insert'; record.payload = payload; return query },
                update(payload) { record.operation = 'update'; record.payload = payload; return query },
                maybeSingle: execute,
                single: execute,
                then(resolve, reject) { return execute().then(resolve, reject) },
            }
            return query
        },
    }
    const dependencies = {
        exports,
        supabaseAdmin,
        UUID_RE: /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
        requireStdUser: async () => ({ ok: true, requester: { email: ownerEmail } }),
        NextResponse: { json: (body, init) => Response.json(body, init) },
        runTts: async (body, auth, resolvedProject) => {
            providerCalls.push({ body, email: auth.requester.email, project: resolvedProject })
            return Response.json({ success: true, prepared: body.voice_segments.length })
        },
        setTimeout: callback => { callback(); return 1 },
    }
    new Function(...Object.keys(dependencies), compiled)(...Object.values(dependencies))
    const post = async (id = projectId) => {
        const response = await exports.POST(new Request('https://studio.example.test/api/tts/generate', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'prepare_narration_segments', voice_segments: [{ text: 'Saved line', voice_id: 'existing-voice' }] }),
        }), { params: { projectId: id } })
        return { response, payload: await response.json() }
    }
    return { post, calls, providerCalls }
}

async function expectDatabaseFailure(h, message, id = projectId) {
    const { response, payload } = await h.post(id)
    assert(response.status >= 500, `Expected a database failure, got ${response.status}`)
    assert.equal(payload.success, false)
    assert.equal(payload.code, 'project_lookup_failed')
    assert.equal(payload.stage, 'load_project')
    assert.match(String(payload.error), new RegExp(message.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
    assert.notEqual(payload.error, 'Project not found')
    assert.equal(h.providerCalls.length, 0, 'No synthesis or assembly after a failed lookup')
    return payload
}

test('the current UUID reaches synthesis with the same resolved project and requester', async () => {
    const h = harness([ok(project)])
    const { response } = await h.post()
    assert.equal(response.status, 200)
    assert.equal(h.calls.length, 1)
    assert.deepEqual(h.calls[0].filters, [['id', projectId], ['employee_email', ownerEmail]])
    assert.equal(h.providerCalls.length, 1)
    assert.equal(h.providerCalls[0].project, project)
    assert.equal(h.providerCalls[0].email, ownerEmail)
})

test('a genuinely missing UUID returns 404 without provisioning or synthesis', async () => {
    const h = harness([ok(null), ok(null)])
    const { response, payload } = await h.post()
    assert.equal(response.status, 404)
    assert.equal(payload.error, 'Project not found')
    assert.equal(h.calls.length, 2)
    assert(h.calls.every(call => call.operation === 'read' && call.table === 'std_projects'))
    assert.equal(h.providerCalls.length, 0)
})

test('a transient returned network error retries only the read and synthesizes once', async () => {
    const h = harness([failed('TypeError: fetch failed', 0), ok(project)])
    assert.equal((await h.post()).response.status, 200)
    assert.equal(h.calls.length, 2)
    assert.deepEqual(h.calls[0], h.calls[1], 'Retry must repeat the same ownership lookup')
    assert.equal(h.providerCalls.length, 1)
})

test('a thrown network error is retried before any provider call', async () => {
    const h = harness([new TypeError('fetch failed'), ok(project)])
    assert.equal((await h.post()).response.status, 200)
    assert.equal(h.calls.length, 2)
    assert.equal(h.providerCalls.length, 1)
})

for (const status of [408, 429, 502, 503]) {
    test(`transient HTTP ${status} retries the database read`, async () => {
        const h = harness([failed('Temporary database problem', status), ok(project)])
        assert.equal((await h.post()).response.status, 200)
        assert.equal(h.calls.length, 2)
        assert.equal(h.providerCalls.length, 1)
    })
}

for (const code of ['ECONNRESET', 'ETIMEDOUT']) {
    test(`${code} retries without provisioning or duplicate synthesis`, async () => {
        const h = harness([failed('Network connection interrupted', 0, code), ok(project)])
        assert.equal((await h.post()).response.status, 200)
        assert.equal(h.calls.length, 2)
        assert.equal(h.providerCalls.length, 1)
        assert(h.calls.every(call => call.operation === 'read'))
    })
}

test('a terminal owner lookup error is preserved and never falls through to provisioning', async () => {
    const h = harness([failed('permission denied for table std_projects', 403, '42501')])
    await expectDatabaseFailure(h, 'permission denied', 'proj-123')
    assert.equal(h.calls.length, 1)
})

test('an exhausted transient lookup surfaces the real error rather than a false missing project', async () => {
    const h = harness(Array.from({ length: 3 }, () => failed('TypeError: fetch failed', 0)))
    await expectDatabaseFailure(h, 'fetch failed')
    assert.equal(h.calls.length, 3, 'Read retries must be bounded')
    assert(h.calls.every(call => call.operation === 'read'))
})

test('a transient fallback read retries that lookup without restarting or duplicating synthesis', async () => {
    const h = harness([ok(null), failed('Temporary database problem', 503), ok(project)])
    assert.equal((await h.post()).response.status, 200)
    assert.equal(h.calls.length, 3)
    assert.deepEqual(h.calls[1], h.calls[2])
    assert.equal(h.providerCalls.length, 1)
})

test('a terminal fallback error is not hidden by a topic lookup or new project', async () => {
    const h = harness([ok(null), failed('invalid API key', 401, 'PGRST301')])
    await expectDatabaseFailure(h, 'invalid API key', 'proj-123')
    assert.equal(h.calls.length, 2)
    assert(h.calls.every(call => call.table === 'std_projects' && call.operation === 'read'))
})

test('a failed topic lookup never creates a replacement project', async () => {
    const h = harness([ok(null), ok(null), failed('permission denied for table topics_queue', 403, '42501')])
    await expectDatabaseFailure(h, 'permission denied', 'proj-123')
    assert.equal(h.calls.length, 3)
    assert.equal(h.calls[2].table, 'topics_queue')
    assert(h.calls.every(call => call.operation === 'read'))
})

test('an uncertain provision insert is reported and never automatically retried', async () => {
    const topic = { id: 123, generated_title: 'Fixture', pregenerated_structure: { scenes: [] } }
    const h = harness([ok(null), ok(null), ok(topic), failed('insert connection lost', 503)])
    await expectDatabaseFailure(h, 'insert connection lost', 'proj-123')
    assert.equal(h.calls.filter(call => call.operation === 'insert').length, 1)
    assert.equal(h.calls.filter(call => call.operation === 'update').length, 0)
})


test('a non-network thrown read error is surfaced without retry or synthesis', async () => {
    const h = harness([new Error('database configuration is invalid')])
    await expectDatabaseFailure(h, 'database configuration is invalid')
    assert.equal(h.calls.length, 1)
})

test('an exhausted thrown network failure produces a structured 503', async () => {
    const h = harness(Array.from({ length: 3 }, () => new TypeError('fetch failed')))
    const { response, payload } = await h.post()
    assert.equal(response.status, 503)
    assert.equal(payload.code, 'project_lookup_failed')
    assert.equal(payload.stage, 'load_project')
    assert.match(payload.error, /fetch failed/)
    assert.equal(h.calls.length, 3)
    assert.equal(h.providerCalls.length, 0)
})

test('recovering a topic read provisions once and calls synthesis once', async () => {
    const topic = { id: 123, generated_title: 'Fixture', pregenerated_structure: { scenes: [] } }
    const h = harness([ok(null), ok(null), failed('Temporary database problem', 502), ok(topic), ok(project), ok(null)])
    assert.equal((await h.post('proj-123')).response.status, 200)
    assert.deepEqual(h.calls[2], h.calls[3])
    assert.equal(h.calls.filter(call => call.operation === 'insert').length, 1)
    assert.equal(h.calls.filter(call => call.operation === 'update').length, 1)
    assert.equal(h.providerCalls.length, 1)
    assert.equal(h.providerCalls[0].project, project)
})
