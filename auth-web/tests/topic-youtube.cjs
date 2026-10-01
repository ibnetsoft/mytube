const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const compile = file => ts.transpileModule(fs.readFileSync(path.join(__dirname, file), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
const lib = {}
new Function('exports', compile('../lib/topicYoutube.ts'))(lib)
const options = lib.parseTopicYoutubeOptions(new URLSearchParams('q=昔話&language=ja&order=viewCount&period=week'))
for (const invalid of ['q=' + 'a'.repeat(121), 'language=xx', 'order=rating', 'period=year']) assert.throws(() => lib.parseTopicYoutubeOptions(new URLSearchParams(invalid)))
const rows = [
    { id: 'abcdefghijk', snippet: { title: '옛날이야기 가족 비밀', channelTitle: '채널', publishedAt: '2026-09-25T00:00:00Z', tags: ['가족', '가족', '옛날이야기'] }, statistics: { viewCount: '12500' } },
    { id: 'lmnopqrstuv', snippet: { title: '가족의 약속', channelTitle: '다른 채널', tags: ['가족'] } },
]
;(async () => {
    const calls = []
    const fetcher = async url => {
        calls.push(new URL(url))
        return Response.json(url.includes('/search?') ? { items: [{ id: { videoId: 'lmnopqrstuv' } }, { id: { videoId: 'abcdefghijk' } }] } : { items: rows })
    }
    const result = await lib.fetchTopicYoutube(options, ['secret'], fetcher, Date.parse('2026-10-01T00:00:00Z'))
    assert.equal(calls[0].searchParams.get('relevanceLanguage'), 'ja')
    assert.equal(calls[0].searchParams.get('regionCode'), 'JP')
    assert.equal(calls[0].searchParams.get('publishedAfter'), '2026-09-24T00:00:00.000Z')
    assert.equal(calls[0].searchParams.get('type'), 'video')
    assert.deepEqual(result.videos.map(video => video.id), ['lmnopqrstuv', 'abcdefghijk'])
    assert.equal(result.videos[1].views, '12500')
    assert.equal(result.videos[0].views, null)
    assert.equal(result.videos[1].url, 'https://www.youtube.com/watch?v=abcdefghijk')
    assert.equal(result.keywords.find(keyword => keyword.text === '가족').count, 2)
    assert(!JSON.stringify(result).includes('secret'))
    const empty = await lib.fetchTopicYoutube(options, ['key'], async () => Response.json({ items: [] }))
    assert.deepEqual(empty.videos, [])
    const popularCalls = []
    await lib.fetchTopicYoutube({ ...options, query: '' }, ['key'], async url => { popularCalls.push(new URL(url)); return Response.json({ items: rows }) })
    assert.equal(popularCalls.length, 1)
    assert.equal(popularCalls[0].searchParams.get('chart'), 'mostPopular')
    const fallback = []
    await lib.fetchTopicYoutube({ ...options, query: '' }, ['expired', 'working'], async url => {
        fallback.push(new URL(url).searchParams.get('key'))
        return fallback.length === 1 ? Response.json({ error: { errors: [{ reason: 'quotaExceeded' }] } }, { status: 403 }) : Response.json({ items: rows })
    })
    assert.deepEqual(fallback, ['expired', 'working'])
    await assert.rejects(lib.fetchTopicYoutube(options, []), /키가 설정/)
    await assert.rejects(lib.fetchTopicYoutube(options, ['secret'], async () => Response.json({ error: { message: 'secret raw error', errors: [{ reason: 'quotaExceeded' }] } }, { status: 403 })), error => error.status === 503 && !error.message.includes('secret'))
    let authorized = false, settingsReads = 0
    const route = {}
    new Function('exports', 'require', compile('../app/api/std/topic-youtube/route.ts'))(route, id => {
        if (id === 'next/server') return { NextResponse: { json: (body, opts = {}) => ({ body, status: opts.status || 200 }) } }
        if (id.endsWith('stdWeb')) return { requireStdUser: async () => authorized ? { ok: true } : { ok: false, response: { status: 401 } } }
        if (id.endsWith('topicYoutube')) return { ...lib, fetchTopicYoutube: async () => result }
        if (id.endsWith('supabaseAdmin')) return { supabaseAdmin: { from: () => ({ select() { return this }, async in() { settingsReads++; return { data: [{ key: 'sys_api_youtube', value: 'secret' }] } } }) } }
        throw Error(id)
    })
    assert.equal((await route.GET(new Request('https://test.invalid'))).status, 401)
    assert.equal(settingsReads, 0)
    authorized = true
    assert.equal((await route.GET(new Request('https://test.invalid?language=evil'))).status, 400)
    assert.equal(settingsReads, 0)
    const response = await route.GET(new Request('https://test.invalid?q=test'))
    assert.equal(response.status, 200)
    assert(!JSON.stringify(response.body).includes('secret'))
    console.log('PASS: YouTube authentication, filters, details/order, actual keyword frequency, empty results, key fallback and sanitized errors')
})().catch(error => { console.error(error); process.exitCode = 1 })
