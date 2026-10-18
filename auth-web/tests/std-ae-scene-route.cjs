const test = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript')
const helper = require('./load-ts.cjs')(path.join(__dirname, '../lib/stdAeScenePreparation.ts'))

function fixture() {
    const state = { authorized: true, owned: true, failInsert: false, attempts: [],
        project: { id: 'p', status: 'draft', updated_at: '2026-10-01', project_payload: {} },
        scenes: [{ scene_number: 1, scene_text: '바람이 분다.' }],
        assets: [{ id: 'psd', scene_number: 1, asset_type: 'original', status: 'uploaded', file_name: 'scene.psd',
            created_at: '2026-10-01', metadata: { gcs_bucket: 'b', gcs_path: 'scene.psd' } }] }
    const db = { from(table) {
        const filters = {}, q = {
            select() { return q }, eq(k, v) { filters[k] = v; return q },
            async maybeSingle() {
                assert.equal(table, 'std_projects'); assert.equal(filters.employee_email, 'owner@example.com')
                return { data: state.owned ? state.project : null }
            },
            async order(key) { assert.equal(key, 'scene_number'); return { data: state.scenes } },
            insert(value) { q.inserted = value; return q },
            async single() {
                state.attempts.push(q.inserted.id)
                if (state.failInsert) { state.failInsert = false; return { error: { message: 'transient database failure' } } }
                if (state.assets.some(a => a.id === q.inserted.id)) return { error: { code: '23505' } }
                const data = { ...q.inserted, created_at: '2026-10-17T01:00:00Z' }
                state.assets.push(data); return { data }
            },
        }; return q
    } }
    const exports = {}, source = fs.readFileSync(path.join(__dirname, '../app/api/std/projects/[projectId]/ae-scene/route.ts'), 'utf8')
    new Function('exports', 'require', ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText)(exports, name => ({
        'next/server': { NextResponse: { json: (body, init = {}) => ({ body, status: init.status || 200 }) } },
        '@/lib/supabaseAdmin': { supabaseAdmin: db },
        '@/lib/stdWeb': { requireStdUser: async () => state.authorized ? { ok: true, requester: { email: 'owner@example.com', user: { id: 'u' } } } : { ok: false, response: { status: 401 } } },
        '@/lib/stdProjectAssets': { loadStdProjectAssets: async () => ({ data: [...state.assets] }) },
        '@/lib/stdAeScenePreparation': helper,
    })[name])
    const submit = body => exports.POST({ json: async () => ({ action: 'prepare', scene_number: 1, source_asset_id: 'psd', direction_text: '머리카락 끝만 움직여 주세요.', ...body }) }, { params: { projectId: 'p' } })
    return { state, submit }
}

test('preparation requires authentication, ownership, and an editable project', async () => {
    const f = fixture(); f.state.authorized = false
    assert.equal((await f.submit()).status, 401)
    f.state.authorized = true; f.state.owned = false
    assert.equal((await f.submit()).status, 404)
    f.state.owned = true; f.state.project.submitted_at = '2026-10-17'
    assert.equal((await f.submit()).status, 409)
    assert.equal(f.state.attempts.length, 0)
})

test('retry after interrupted insert recovers without a permanent claim or duplicate job', async () => {
    const f = fixture(); f.state.failInsert = true
    assert.equal((await f.submit()).status, 400)
    assert.equal((await f.submit()).status, 202)
    assert.equal(f.state.attempts[0], f.state.attempts[1])
    assert.equal((await f.submit()).status, 200)
    assert.equal(f.state.assets.filter(a => a.metadata.kind === 'ae_scene_preparation').length, 1)
})

test('source changes and invalid directions cannot queue an unreviewable request', async () => {
    const f = fixture()
    for (const body of [{ source_asset_id: 'old' }, { direction_text: ' ' }, { direction_text: 'x'.repeat(4001) }, { scene_number: 2 }])
        assert.equal((await f.submit(body)).status, 400)
    assert.equal(f.state.attempts.length, 0)
})

test('disable records a new selection and a later prepare can create a fresh job', async () => {
    const f = fixture()
    assert.equal((await f.submit()).status, 202)
    assert.equal((await f.submit({ action: 'disable' })).status, 200)
    // Database timestamps increase in real inserts; make that ordering explicit here.
    f.state.assets[2].created_at = '2026-10-17T01:00:01Z'
    assert.equal(helper.aeSceneSelections(f.state.assets).get(1).metadata.enabled, false)
    assert.equal((await f.submit()).status, 202)
    assert.equal(new Set(f.state.attempts).size, 3)
})

test('effect selection survives queued requests and retries without duplicate jobs', async () => {
    const f = fixture()
    assert.equal((await f.submit({ requested_effects: ['focus_glow', 'atmospheric_haze'] })).status, 202)
    const input = f.state.assets[1].metadata.input
    assert.deepEqual(input.requested_effects, ['atmospheric_haze', 'focus_glow'])
    assert.equal((await f.submit({ requested_effects: ['atmospheric_haze', 'focus_glow'] })).status, 200)
    assert.equal(f.state.assets.length, 2)
    for (const requested_effects of [['unknown'], ['focus_glow', 'focus_glow'], null, 'focus_glow'])
        assert.equal((await f.submit({ requested_effects })).status, 400)
    assert.equal(f.state.assets.length, 2)
})
