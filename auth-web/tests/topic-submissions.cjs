const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const path = require('node:path')
const compile = file => ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const lib = {}
new Function('exports', compile(path.join(__dirname, '../lib/topicSubmission.ts')))(lib)
const valid = { title: '토픽', story: '줄거리', category: '이야기', duration_minutes: 15, language: 'ko', production_mode: 'standard', setting_country: '한국', era_region: '현대', image_style: '실사' }
assert.equal(lib.validateTopicSubmission(valid).title, '토픽')
assert.equal(lib.validateTopicSubmission(valid).ae_scene_delivery, 'gcs')
assert.equal(lib.validateTopicSubmission({ ...valid, ae_scene_delivery: 'gcs' }).ae_scene_delivery, 'gcs')
for (const change of [{ title: ' ' }, { duration_minutes: 0 }, { language: 'xx' }, { ae_scene_delivery: '' }, { ae_scene_delivery: 'other' }, { youtube_url: 'https://evil.example/watch?v=abcdefghijk' }, { character_images: [{ name: 'x', data: 'data:image/png;base64,YQ==' }] }]) {
    assert.throws(() => lib.validateTopicSubmission({ ...valid, ...change }))
}
assert.equal(lib.validateTopicSubmission({ ...valid, youtube_url: 'https://youtu.be/abcdefghijk' }).youtube_url, 'https://youtu.be/abcdefghijk')
let authorized = true, inserted = 0, filters = [], insertedRows = [], getRows = []
const route = {}
new Function('exports', 'require', compile(path.join(__dirname, '../app/api/std/topic-submissions/route.ts')))(route, id => {
    if (id === 'next/server') return { NextResponse: { json: (body, opts = {}) => ({ body, status: opts.status || 200 }) } }
    if (id === 'crypto') return require('node:crypto')
    if (id.endsWith('topicSubmission')) return lib
    if (id.endsWith('stdWeb')) return { requireStdUser: async () => authorized ? { ok: true, requester: { email: 'Owner@Test.invalid' } } : { ok: false, response: { status: 401 } } }
    if (id.endsWith('supabaseAdmin')) return { supabaseAdmin: { from: table => ({
        select() { return this }, eq(k, v) { filters.push([k, v]); return this }, order() { return table === 'categories' ? Promise.resolve({ data: [{ id: 2, name: '옛날이야기' }, { id: 13, name: '日本昔話' }] }) : this },
        async limit() { return { data: getRows } }, async insert(row) { inserted++; insertedRows.push(row); assert.equal(row.owner_email, 'owner@test.invalid'); assert(!row.status); return {} },
    }) } }
    throw Error(id)
})
const call = body => route.POST(new Request('https://test.invalid', { method: 'POST', headers: { 'Idempotency-Key': '12345678-1234-4234-8234-123456789abc' }, body: JSON.stringify(body) }))
;(async () => {
    authorized = false; assert.equal((await call(valid)).status, 401); assert.equal(inserted, 0)
    authorized = true; assert.equal((await call({ ...valid, story: '' })).status, 400); assert.equal(inserted, 0)
    assert.equal((await call({ ...valid, owner_email: 'attacker', status: 'approved' })).status, 201)
    assert.equal(insertedRows[0].request_data.ae_scene_delivery, 'gcs')
    assert.equal((await call({ ...valid, ae_scene_delivery: 'gcs' })).status, 201)
    assert.equal(insertedRows[1].request_data.ae_scene_delivery, 'gcs')
    getRows = [{ id: 'one', title: '토픽', status: 'pending', job_id: null, review_note: '', created_at: '2026-09-26', request_data: { ae_scene_delivery: 'gcs', character_images: [{ data: 'private-base64' }] } }]
    const listed = await route.GET(new Request('https://test.invalid'))
    assert.equal(listed.body.items[0].ae_scene_delivery, 'gcs')
    assert.deepEqual(listed.body.categories.map(category => category.name), ['옛날이야기', '日本昔話'])
    assert.equal('request_data' in listed.body.items[0], false)
    assert.equal(JSON.stringify(listed.body).includes('private-base64'), false)
    assert(filters.some(([key, value]) => key === 'owner_email' && value === 'owner@test.invalid'))
    console.log('PASS: topic validation, authentication, ownership filtering, and pending-only insertion')
})().catch(error => { console.error(error); process.exitCode = 1 })
