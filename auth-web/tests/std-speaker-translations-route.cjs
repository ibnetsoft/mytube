const assert = require('node:assert/strict')
const { createHash } = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const routePath = path.resolve(__dirname, '../app/api/std/projects/[projectId]/speaker-translations/route.ts')
const routeSource = fs.readFileSync(routePath, 'utf8')
const PROJECT_ID = 'speaker-project'
const OWNER = 'owner@example.test'
const NAMES = ['お鈴', '清次']

function setup({ payload = {}, sourcePayload = {}, authenticated = true, owner = OWNER, jobs = [] } = {}) {
    const tables = {
        std_projects: [{ id: PROJECT_ID, employee_email: owner, project_payload: payload, source_payload: sourcePayload }],
        std_subtitle_translation_jobs: structuredClone(jobs),
        global_settings: [{ key: 'sys_api_subtitle_translation_scope', value: 'all' }],
    }
    const queries = []
    let sequence = 0
    const database = {
        from(table) {
            assert.ok(table in tables, `Unexpected table: ${table}`)
            const filters = []
            let mutation = null
            const operation = { table, filters, action: 'select' }
            queries.push(operation)
            const matching = () => tables[table].filter(row => filters.every(([key, value]) => row[key] === value))
            const execute = () => {
                if (mutation) {
                    for (const row of matching()) Object.assign(row, mutation)
                }
                return { data: matching(), error: null }
            }
            const query = {
                select() { return query },
                eq(key, value) { filters.push([key, value]); return query },
                async maybeSingle() { return { ...execute(), data: matching()[0] || null } },
                async single() { return query.maybeSingle() },
                update(values) { mutation = values; operation.action = 'update'; return query },
                async upsert(values, options = {}) {
                    operation.action = 'upsert'
                    const keys = (options.onConflict || 'id').split(',')
                    const rows = Array.isArray(values) ? values : [values]
                    for (const row of rows) {
                        const existing = tables[table].find(candidate => keys.every(key => candidate[key] === row[key]))
                        if (!existing) tables[table].push({ id: `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`, status: 'queued', ...structuredClone(row) })
                        else if (!options.ignoreDuplicates) Object.assign(existing, structuredClone(row))
                    }
                    return { error: null }
                },
                then(resolve, reject) { return Promise.resolve(execute()).then(resolve, reject) },
            }
            return query
        },
    }
    const dependencies = {
        'next/server': { NextResponse: Response },
        '@/lib/supabaseAdmin': { supabaseAdmin: database },
        '@/lib/stdWeb': {
            requireStdUser: async () => authenticated
                ? { ok: true, requester: { email: OWNER } }
                : { ok: false, response: Response.json({ success: false, error: 'Unauthorized' }, { status: 401 }) },
        },
    }
    const modules = new Map()
    function load(filename) {
        if (modules.has(filename)) return modules.get(filename)
        const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
            compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
        }).outputText
        const exports = {}
        modules.set(filename, exports)
        new Function('exports', 'require', compiled)(exports, name => {
            if (name in dependencies) return dependencies[name]
            if (name.startsWith('@/')) return load(path.resolve(__dirname, '..', `${name.slice(2)}.ts`))
            if (name === 'crypto' || name.startsWith('node:')) return require(name)
            throw new Error(`Unexpected dependency: ${name}`)
        })
        return exports
    }
    const route = load(routePath)
    async function post(body = { target_language: 'ko', names: NAMES }, headers = {}) {
        const request = new Request(`https://studio.example/api/std/projects/${PROJECT_ID}/speaker-translations`, {
            method: 'POST',
            body: typeof body === 'string' ? body : JSON.stringify(body),
            headers: { 'Content-Type': 'application/json', ...headers },
        })
        const response = await route.POST(request, { params: { projectId: PROJECT_ID } })
        return { status: response.status, data: await response.json() }
    }
    return { tables, queries, post }
}

test('speaker translations require authentication and project ownership before touching jobs', async () => {
    for (const [options, expected] of [[{ authenticated: false }, 401], [{ owner: 'other@example.test' }, 404]]) {
        const state = setup(options)
        assert.equal((await state.post()).status, expected)
        assert.equal(state.queries.filter(query => query.table === 'std_subtitle_translation_jobs').length, 0)
    }
})

test('speaker translations reject malformed languages and name payloads', async () => {
    const invalid = [
        '{invalid',
        { target_language: 'en', names: NAMES },
        { target_language: 'ja', names: NAMES },
        { target_language: 'ko', names: 'お鈴' },
        { target_language: 'ko', names: [] },
        { target_language: 'ko', names: ['   '] },
        { target_language: 'ko', names: [null] },
        { target_language: 'ko', names: [42] },
        { target_language: 'ko', names: ['名'.repeat(81)] },
        { target_language: 'ko', names: Array.from({ length: 101 }, (_, index) => `name ${index}`) },
        { target_language: 'ko', names: ['お鈴', ' お鈴 '] },
        { target_language: 'ko', names: ['清\n次'] },
        { target_language: 'ko', names: NAMES, job_id: 'invalid-job' },
    ]
    for (const body of invalid) {
        const state = setup()
        assert.equal((await state.post(body)).status, 400, JSON.stringify(body).slice(0, 100))
        assert.equal(state.tables.std_subtitle_translation_jobs.length, 0)
    }
})

test('cached names return their original identity keys without queuing or using subtitle translations', async () => {
    const payload = {
        speaker_name_translations: { ko: { お鈴: '오스즈', 清次: '세이지', 無関係: '무관계' } },
        subtitle_translations: { ko: { blocks: [{ index: 0, source_text: 'お鈴', translated_text: 'subtitle cache must stay separate' }] } },
    }
    const before = structuredClone(payload)
    const state = setup({ payload })
    const response = await state.post()
    assert.equal(response.status, 200)
    assert.equal(response.data.success, true)
    assert.equal(response.data.provider, 'local-codex')
    assert.deepEqual(response.data.translations, { お鈴: '오스즈', 清次: '세이지' })
    assert.deepEqual(payload, before)
    assert.equal(state.queries.filter(query => query.table === 'std_subtitle_translation_jobs').length, 0)
})

test('existing localized character names are reused from both project and source metadata', async () => {
    const state = setup({
        payload: { structure: { character_anchors: { main_character: { name: 'お鈴', name_th: 'โอซุสุ' } } } },
        sourcePayload: { structure: { character_anchors: { supporting_characters: [{ name: '清次', name_th: 'เซจิ' }] } } },
    })
    const response = await state.post({ target_language: 'th', names: NAMES })
    assert.equal(response.status, 200)
    assert.deepEqual(response.data.translations, { お鈴: 'โอซุสุ', 清次: 'เซจิ' })
    assert.equal(state.tables.std_subtitle_translation_jobs.length, 0)
})

test('queued readings include character/story context and allow newly assigned manual speakers', async () => {
    const state = setup({ payload: { structure: {
        character_anchors: { main_character: { name: '清次', reading: 'せいじ', gender: 'male', role: '若い商人' } },
        dialogue_annotations: { scenes: [{ source_text: '清次は静かに戸を開いた。', spans: [{ speaker: '清次' }] }] },
    } } })
    const response = await state.post({ target_language: 'ko', names: ['清次', '手動の人物'] })
    assert.equal(response.status, 202)
    const blocks = state.tables.std_subtitle_translation_jobs[0].source_blocks
    assert.equal(blocks.length, 2)
    assert.equal(blocks.find(block => block.source_text === '清次').context.reading, 'せいじ')
    assert.ok(JSON.stringify(blocks).includes('清次は静かに戸を開いた。'))
    assert.ok(blocks.some(block => block.source_text === '手動の人物'))
})

test('queues only missing names in a separate job namespace and returns cached names while pending', async () => {
    const state = setup({ payload: { speaker_name_translations: { ko: { お鈴: '오스즈' } } } })
    const response = await state.post()
    assert.equal(response.status, 202)
    assert.equal(response.data.pending, true)
    assert.equal(response.data.provider, 'local-codex')
    assert.deepEqual(response.data.translations, { お鈴: '오스즈' })
    assert.equal(state.tables.std_subtitle_translation_jobs.length, 1)
    const job = state.tables.std_subtitle_translation_jobs[0]
    assert.equal(response.data.job_id, job.id)
    assert.equal(job.project_id, PROJECT_ID)
    assert.equal(job.target_language, 'ko')
    assert.equal(job.translation_kind, 'speaker_names')
    assert.deepEqual(job.source_blocks.map(block => block.source_text), ['清次'])
    assert.ok(job.source_blocks.every(block => Number.isInteger(block.index)))
    const subtitleHash = createHash('sha256').update(JSON.stringify(job.source_blocks)).digest('hex')
    assert.notEqual(job.request_hash, subtitleHash, 'Speaker jobs must not collide with the subtitle request namespace')
    const again = await state.post({ target_language: 'ko', names: [...NAMES].reverse() })
    assert.equal(again.data.job_id, job.id)
    assert.equal(state.tables.std_subtitle_translation_jobs.length, 1, 'Repeated opens and reordered names reuse the queued job')
})

test('polling merges completed names with the cache and preserves Japanese identity keys', async () => {
    const state = setup({ payload: { speaker_name_translations: { ko: { お鈴: '오스즈' } } } })
    const queued = await state.post()
    const job = state.tables.std_subtitle_translation_jobs[0]
    const input = { target_language: 'ko', names: NAMES, job_id: queued.data.job_id }
    const pending = await state.post(input)
    assert.equal(pending.status, 202)
    assert.equal(pending.data.pending, true)
    assert.deepEqual(pending.data.translations, { お鈴: '오스즈' })
    job.status = 'completed'
    job.result_blocks = job.source_blocks.map(block => ({ ...block, translated_text: '세이지' }))
    const completed = await state.post(input)
    assert.equal(completed.status, 200)
    assert.equal(completed.data.success, true)
    assert.deepEqual(completed.data.translations, { お鈴: '오스즈', 清次: '세이지' })
    assert.equal(completed.data.provider, 'local-codex')
    assert.equal((await state.post({ ...input, names: ['お鈴', '別人'] })).status, 409)
})

test('speaker polling cannot read subtitle jobs or another project/language', async () => {
    for (const mutation of [
        { translation_kind: 'subtitles' },
        { project_id: 'another-project' },
        { target_language: 'th' },
    ]) {
        const state = setup()
        const queued = await state.post()
        const job = state.tables.std_subtitle_translation_jobs[0]
        Object.assign(job, mutation, {
            status: 'completed',
            result_blocks: job.source_blocks.map(block => ({ ...block, translated_text: 'must not leak' })),
        })
        const result = await state.post({ target_language: 'ko', names: NAMES, job_id: queued.data.job_id })
        assert.equal(result.status, 409, JSON.stringify(mutation))
        assert.equal(result.data.success, false)
    }
})

test('failed local jobs report a failure instead of publishing partial names', async () => {
    const state = setup()
    const queued = await state.post({ target_language: 'th', names: NAMES })
    const job = state.tables.std_subtitle_translation_jobs[0]
    job.status = 'failed'
    job.error = 'Local translation failed'
    const result = await state.post({ target_language: 'th', names: NAMES, job_id: queued.data.job_id })
    assert.equal(result.status, 502)
    assert.equal(result.data.success, false)
    assert.equal(result.data.error, job.error)
})

test('speaker translation route only queues the local worker and never calls a model API', () => {
    assert.doesNotMatch(routeSource, /generateJsonWithModelSetting|geminiApiKey|OPENAI_API_KEY|GEMINI_API_KEY|generativelanguage\.googleapis|api\.openai\.com/)
})
