const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const ts = require('typescript')
const path = require('node:path')
const source = fs.readFileSync(path.resolve(__dirname, '../app/api/std/projects/[projectId]/assets/file/route.ts'), 'utf8')
function setup(status = 200) {
    let fetched = 0, range
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array([1, 2, 3])); controller.close() } })
    const db = { from(table) { const q = new Proxy({}, { get(_, key) {
        if (key === 'then') return resolve => resolve({ data: table === 'std_projects' ? { id: 'project' } : { id: 'clip', asset_type: 'video', metadata: { gcs_path: 'clip.mp4', storage_provider: 'gcs' } } })
        return () => q
    } }); return q } }
    const result = {}
    class NextResponse extends Response { static json(value, init) { return new Response(JSON.stringify(value), init) } }
    vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, {
        exports: result, Request, URL, Buffer, console,
        fetch: async (_, options) => { fetched++; range = options.headers.Range; return { ok: true, status, body: stream,
            headers: new Headers({ 'content-type': 'video/mp4', 'content-length': '5734610', ...(status === 206 ? {'content-range':'bytes 0-99/5734610'} : {}) }),
            arrayBuffer() { throw new Error('Must not buffer the whole clip on the server') } } },
        require: name => name === 'next/server' ? { NextResponse } : name.includes('supabaseAdmin') ? { supabaseAdmin: db }
            : name.includes('stdWeb') ? { requireStdUser: async () => ({ok: true, requester: {email: 'owner@example.test'}}) }
            : name.includes('stdAssetStorage') ? {assetStorageRef: () => ({path: 'clip.mp4'})}
            : {isGcsConfiguredAsync: async () => true, createGcsSignedReadUrl: async () => 'https://storage.example/clip'},
    })
    return { get: () => result.GET(new Request('https://local/api?assetId=clip', { headers: status === 206 ? {Range:'bytes=0-99'} : {} }), {params: {projectId:'e9233112-f0d7-4b35-91bf-2f892844eb30'}}), stream, fetched: () => fetched, range: () => range }
}
test('a full 5 MB clip is streamed without reading it into the server buffer', async () => {
    const fixture = setup()
    const response = await fixture.get()
    assert.equal(response.status, 200)
    assert.equal(response.body, fixture.stream)
    assert.equal(response.headers.get('content-type'), 'video/mp4')
    assert.equal(response.headers.get('content-length'), '5734610')
    assert.equal(fixture.fetched(), 1)
})
test('streaming preserves byte-range delivery', async () => {
    const fixture = setup(206)
    const response = await fixture.get()
    assert.equal(response.status, 206)
    assert.equal(fixture.range(), 'bytes=0-99')
    assert.equal(response.headers.get('content-range'), 'bytes 0-99/5734610')
})
