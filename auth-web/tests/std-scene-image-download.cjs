const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')
const sharp = require('sharp')
function load(file, dependencies = {}, globals = {}) {
    const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    }).outputText
    const exports = {}
    new Function('exports', 'require', ...Object.keys(globals), code)(exports, name => {
        if (!(name in dependencies)) throw new Error(`Unexpected dependency ${name}`)
        return dependencies[name]
    }, ...Object.values(globals))
    return exports
}
const projectId = 'e9233112-f0d7-4b35-91bf-2f892844eb30'
const objectPath = 'topics/3373/images/scene-006-original.png'
const proxy = `/api/std/assets/gcs-file?${new URLSearchParams({ bucket: 'air-studio-prod', path: objectPath })}`
const scene = { scene_number: 6, metadata: { image_url: proxy, metadata: { cowork_image_asset: { storage_provider: 'gcs', bucket: 'air-studio-prod', gcs_path: objectPath } } } }
const request = () => new Request(`https://studio.example/api/std/projects/${projectId}/scene-image?sceneNumber=6`, { headers: { authorization: 'Bearer fixture-token', cookie: 'fixture-cookie', 'x-impersonate-email': 'owner@example.com' } })
const media = load('lib/stdSceneMediaUrl.ts')
async function png() { return sharp({ create: { width: 1920, height: 1080, channels: 3, background: '#aaff33' } }).png().toBuffer() }
function reader(downloadGcsObject, fetch = () => { throw new Error('Unexpected self-fetch') }) {
    return load('lib/stdSceneImageDownload.ts', { sharp, './gcsStorage': { downloadGcsObject }, './stdSceneMediaUrl': media }, { fetch })
}
function route(name, imageReader, auth = { ok: true, requester: { email: 'owner@example.com' } }) {
    const filters = []
    const supabaseAdmin = { from(table) {
        const data = table === 'std_projects' ? { id: projectId, project_payload: {} } : (name === 'scene-image' ? scene : [scene])
        const result = { data, error: null }
        const query = { select: () => query, eq: (...args) => { filters.push([table, ...args]); return query }, order: () => query, in: () => query, maybeSingle: async () => result, then: (resolve, reject) => Promise.resolve(result).then(resolve, reject) }
        return query
    } }
    return { filters, ...load(`app/api/std/projects/[projectId]/${name}/route.ts`, {
        'next/server': { NextResponse: Response }, '@/lib/supabaseAdmin': { supabaseAdmin }, '@/lib/stdWeb': { requireStdUser: async () => auth },
        '@/lib/stdSceneMediaUrl': media, '@/lib/stdSceneImageDownload': imageReader,
    }) }
}
test('reported relative GCS image downloads original PNG bytes through project ownership checks', async () => {
    const original = await png(), calls = []
    const api = route('scene-image', reader(async ref => { calls.push(ref); return original }))
    const response = await api.GET(request(), { params: { projectId } })
    assert.equal(response.status, 200)
    assert.deepEqual(calls, [{ bucket: 'air-studio-prod', objectPath }])
    assert(api.filters.some(([table, key, value]) => table === 'std_projects' && key === 'employee_email' && value === 'owner@example.com'))
    assert.equal(response.headers.get('content-type'), 'image/png')
    assert.match(response.headers.get('content-disposition'), /scene-006.png/)
    const bytes = Buffer.from(await response.arrayBuffer())
    assert.deepEqual(bytes, original)
    assert.equal((await sharp(bytes).metadata()).width, 1920)
    await sharp(bytes).raw().toBuffer()
})
test('legacy GCS and payload metadata resolve to the original object', async () => {
    const calls = [], read = reader(async ref => { calls.push(ref); return png() }).readSceneImage
    await read(request(), {}, { image_url: `https://db.example/storage/v1/object/public/air-studio-prod/${objectPath}` })
    await read(request(), { metadata: { metadata: { cowork_image_asset: { storage_provider: 'gcs', bucket: 'air-studio-prod', object_path: objectPath } } } })
    assert.equal(calls.length, 2)
    assert(calls.every(ref => ref.objectPath === objectPath))
})
test('JPEG bytes override misleading PNG URL/header without sending credentials externally', async () => {
    const bytes = await sharp(await png()).jpeg().toBuffer()
    const read = reader(null, async (url, options) => {
        assert.equal(url.href, 'https://images.example/image.png')
        assert.equal(options.headers.get('authorization'), null)
        assert.equal(options.headers.get('cookie'), null)
        return new Response(bytes, { headers: { 'content-type': 'image/png' } })
    }).readSceneImage
    const image = await read(request(), { image_url: 'https://images.example/image.png' })
    assert.equal(image.extension, 'jpg')
    assert.equal(image.contentType, 'image/jpeg')
    assert.deepEqual(image.buffer, bytes)
})
test('other same-origin assets receive authentication', async () => {
    const read = reader(null, async (url, options) => {
        assert.equal(url.origin, 'https://studio.example')
        assert.equal(options.headers.get('authorization'), 'Bearer fixture-token')
        assert.equal(options.headers.get('x-impersonate-email'), 'owner@example.com')
        return new Response(await png())
    }).readSceneImage
    await read(request(), { image_url: '/api/std/assets/file?id=fixture' })
})
test('HTML, empty bytes and failed storage reads never become image attachments', async () => {
    for (const getBytes of [async () => Buffer.from('<html>Error</html>'), async () => Buffer.alloc(0), async () => { throw new Error('Storage unavailable') }]) {
        const api = route('scene-image', reader(getBytes))
        const response = await api.GET(request(), { params: { projectId } })
        assert.equal(response.status, 502)
        assert.equal(response.headers.get('content-disposition'), null)
        assert.equal((await response.json()).success, false)
    }
})
test('unauthenticated requests cannot read storage', async () => {
    const api = route('scene-image', reader(() => { throw new Error('must not be called') }), { ok: false, response: Response.json({ error: 'Authentication required' }, { status: 401 }) })
    assert.equal((await api.GET(request(), { params: { projectId } })).status, 401)
})
test('ZIP includes original bytes and filenames; failures abort rather than silently omit images', async () => {
    const original = await png()
    const api = route('scene-images', reader(async () => original))
    const response = await api.GET(request(), { params: { projectId } })
    assert.equal(response.status, 200)
    const zip = Buffer.from(await response.arrayBuffer())
    assert.equal(zip.readUInt32LE(0), 0x04034b50)
    const nameLength = zip.readUInt16LE(26)
    assert.equal(zip.subarray(30, 30 + nameLength).toString(), 'scene-006.png')
    assert.deepEqual(zip.subarray(30 + nameLength, 30 + nameLength + original.length), original)
    const broken = route('scene-images', reader(async () => { throw new Error('Storage unavailable') }))
    assert.equal((await broken.GET(request(), { params: { projectId } })).status, 502)
})
test('client honors server filename and never saves JSON or HTML failures', async () => {
    const links = []
    let response = new Response(await png(), { headers: { 'content-type': 'image/png', 'content-disposition': 'attachment; filename="scene-006.png"' } })
    const globals = {
        fetch: async (_, options) => { assert.equal(options.headers.Authorization, 'Bearer fixture'); return response },
        document: { createElement: () => { const el = { click: () => links.push(el), remove() {} }; return el }, body: { appendChild() {} } },
        URL: { createObjectURL: () => 'blob:fixture', revokeObjectURL() {} }, setTimeout: fn => fn(),
    }
    const { downloadStdFile } = load('lib/stdFileDownload.ts', {}, globals)
    await downloadStdFile('/download', { Authorization: 'Bearer fixture' }, 'wrong.jpg', 'image')
    assert.equal(links[0].download, 'scene-006.png')
    response = Response.json({ error: 'Storage unavailable' }, { status: 502 })
    await assert.rejects(downloadStdFile('/download', { Authorization: 'Bearer fixture' }, 'wrong.jpg', 'image'), /Storage unavailable/)
    response = new Response('<html>Error</html>', { headers: { 'content-type': 'text/html' } })
    await assert.rejects(downloadStdFile('/download', { Authorization: 'Bearer fixture' }, 'wrong.jpg', 'image'), /Invalid download response/)
    assert.equal(links.length, 1)
})
