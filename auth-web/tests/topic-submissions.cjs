const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const path = require('node:path')
const compile = file => ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true, target: ts.ScriptTarget.ES2022 } }).outputText
const nv = {}
new Function('exports', compile(path.join(__dirname, '../lib/stdNonverbal.ts')))(nv)
const lib = {}
new Function('exports', 'require', compile(path.join(__dirname, '../lib/topicSubmission.ts')))(lib, name => name === './stdNonverbal' ? nv : require('node:module').createRequire(path.join(__dirname, '../lib/topicSubmission.ts'))(name))
const valid = { title: '토픽', story: '줄거리', category: '이야기', duration_minutes: 15, language: 'ko', production_mode: 'standard', setting_country: '한국', era_region: '현대', image_style: '실사' }
assert.equal(lib.validateTopicSubmission(valid).title, '토픽')
assert.equal(lib.validateTopicSubmission(valid).ae_scene_delivery, 'gcs')
for (const language of ['ko', 'ja', 'en']) {
    const thai = lib.validateTopicSubmission({ ...valid, input_language: 'th', language, story: 'หญิงสาวพบจดหมายเก่าและกลับไปพบครอบครัว', character_notes: 'สุภาพและกล้าหาญ', requirements: 'อย่าเปลี่ยนชื่อของตัวละคร' })
    assert.equal(thai.input_language, 'th')
    assert.equal(thai.language, language)
    assert.equal(thai.story, 'หญิงสาวพบจดหมายเก่าและกลับไปพบครอบครัว')
}
assert.throws(() => lib.validateTopicSubmission({ ...valid, input_language: 'xx' }))
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
    if (id.endsWith('youtubeSourceDuration')) return {fetchYoutubeSourceDuration: async()=>({source_video_id:'abcdefghijk',source_duration_seconds:1007,source_duration_verified:true})}
    if (id.endsWith('topicSubmission')) return lib
    if (id.endsWith('stdWeb')) return { requireStdUser: async () => authorized ? { ok: true, requester: { email: 'Owner@Test.invalid' } } : { ok: false, response: { status: 401 } } }
    if (id.endsWith('supabaseAdmin')) return { supabaseAdmin: { from: table => ({
        select() { return this }, in() { return Promise.resolve({data:[]}) }, eq(k, v) { filters.push([k, v]); return this }, order() { return table === 'categories' ? Promise.resolve({ data: [{ id: 2, name: '옛날이야기' }, { id: 13, name: '日本昔話' }] }) : this },
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
    assert.equal((await call({...valid,image_style:'jp_domestic_watercolor',youtube_url:'https://youtu.be/abcdefghijk',duration_minutes:22,duration_seconds:1})).status,201)
    assert.equal(insertedRows.at(-1).request_data.duration_seconds,1007)
    assert.equal(insertedRows.at(-1).request_data.duration_mode,'source_video')
    getRows = [{ id: 'one', title: '토픽', status: 'pending', job_id: null, review_note: '', created_at: '2026-09-26', request_data: { ae_scene_delivery: 'gcs', character_images: [{ data: 'private-base64' }] } }]
    const listed = await route.GET(new Request('https://test.invalid'))
    assert.equal(listed.body.items[0].ae_scene_delivery, 'gcs')
    assert.deepEqual(listed.body.categories.map(category => category.name), ['옛날이야기', '日本昔話'])
    assert.equal('request_data' in listed.body.items[0], false)
    assert.equal(JSON.stringify(listed.body).includes('private-base64'), false)
    assert(filters.some(([key, value]) => key === 'owner_email' && value === 'owner@test.invalid'))
    console.log('PASS: topic validation, authentication, ownership filtering, and pending-only insertion')
})().catch(error => { console.error(error); process.exitCode = 1 })

const documentary = lib.validateTopicSubmission({ ...valid, image_style: 'sumi_e_ukiyo_e' })
assert.equal(documentary.script_style, 'japanese_historical_documentary')
assert.equal(documentary.language, 'ja')
assert.equal(documentary.duration_minutes, 30)
assert.equal(documentary.setting_country, '일본')
assert.equal(documentary.era_region, '주제 인물의 실제 생존 시대·지역')
const sourcedDocumentary = lib.validateTopicSubmission({ ...valid, image_style: 'sumi_e_ukiyo_e', historical_source_notes: '博物館の資料と確認すべき年代' })
assert.equal(sourcedDocumentary.historical_source_notes, '博物館の資料と確認すべき年代')
assert.throws(() => lib.validateTopicSubmission({ ...valid, image_style: 'sumi_e_ukiyo_e', historical_source_notes: 'x'.repeat(12001) }))
assert.equal(lib.validateTopicSubmission({ ...valid, historical_source_notes: 'unrelated' }).historical_source_notes, '')
assert.equal(lib.validateTopicSubmission(valid).script_style, 'story')

const folktale = lib.validateTopicSubmission({ ...valid, image_style: 'jidaigeki_cel' })
assert.equal(folktale.language, 'ja')
assert.equal(folktale.setting_country, '일본')
assert.equal(folktale.script_style, 'story')
assert.equal(folktale.duration_minutes, 15)

const silent = lib.validateTopicSubmission({ ...valid, production_mode: 'nonverbal_preschool', duration_minutes: 3, image_style: 'anime' })
assert.equal(silent.script_style, 'nonverbal_preschool')
assert.throws(() => lib.validateTopicSubmission({ ...silent, duration_minutes: 11 }))
assert.throws(() => lib.validateTopicSubmission({ ...silent, image_style: 'realistic' }))

const domestic = lib.validateTopicSubmission({ ...valid, category:'옛날이야기', image_style:'jp_domestic_watercolor', language:'ko', duration_minutes:30 })
assert.equal(domestic.category, '일본사건')
assert.equal(domestic.duration_minutes, 30)
assert.equal(domestic.language, 'ja')
assert.equal(domestic.setting_country, '일본')
assert.equal(domestic.script_style, 'japanese_domestic_drama')
assert.equal(lib.validateTopicSubmission({...domestic,duration_minutes:13}).duration_minutes,13)
assert.throws(()=>lib.validateTopicSubmission({...domestic,production_mode:'nonverbal_preschool',duration_minutes:3}))
