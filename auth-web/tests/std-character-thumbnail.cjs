const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

function load(relativePath, dependencies = {}) {
    const filename = path.resolve(__dirname, '..', relativePath)
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText
    const exports = {}
    new Function('exports', 'require', compiled)(exports, name => {
        if (!(name in dependencies)) throw new Error(`Unexpected dependency: ${name}`)
        return dependencies[name]
    })
    return exports
}

const characterProtection = load('lib/stdCharacterProtection.ts')
const characterThumbnail = load('lib/stdCharacterThumbnail.ts')
const characters = Array.from({ length: 23 }, (_, index) => ({
    name: `Character ${index}`,
    image_url: `/api/std/assets/gcs-file?bucket=studio-assets&path=topics/42/characters/character-${index}.png`,
}))
const payload = {
    structure: { character_anchors: { main_character: characters[0], supporting_characters: characters.slice(1) } },
}

function harness({ projectPayload = payload, authenticated = true } = {}) {
    const filters = []
    const downloads = []
    let queries = 0
    const query = {
        select: () => query,
        eq: (key, value) => { filters.push([key, value]); return query },
        maybeSingle: async () => ({ data: projectPayload ? { project_payload: projectPayload } : null, error: null }),
    }
    const route = load('app/api/std/projects/[projectId]/character-thumbnail/route.ts', {
        'next/server': { NextResponse: Response },
        '@/lib/supabaseAdmin': { supabaseAdmin: { from: () => { queries += 1; return query } } },
        '@/lib/stdWeb': {
            requireStdUser: async () => authenticated
                ? { ok: true, requester: { email: 'owner@example.com' } }
                : { ok: false, response: new Response(null, { status: 401 }) },
        },
        '@/lib/stdCharacterProtection': characterProtection,
        '@/lib/stdCharacterThumbnail': characterThumbnail,
        '@/lib/gcsStorage': {
            getGcsConfig: async () => ({}),
            gcsBucketName: () => 'studio-assets',
            downloadGcsObject: async object => { downloads.push(object); return new Uint8Array([1, 2, 3]) },
        },
    })
    return {
        get: search => route.GET(new Request(`https://studio.example/api/std/projects/project-id/character-thumbnail${search}`), {
            params: { projectId: 'project-id' },
        }),
        filters,
        downloads,
        queries: () => queries,
    }
}

test('recurring characters beyond the old slot limit receive their authorized reference image', async () => {
    const app = harness()
    const response = await app.get('?slot=22')
    assert.equal(response.status, 200)
    assert.equal(response.headers.get('content-type'), 'image/png')
    assert.deepEqual(app.filters, [['id', 'project-id'], ['employee_email', 'owner@example.com']])
    assert.deepEqual(app.downloads, [{ bucket: 'studio-assets', objectPath: 'topics/42/characters/character-22.png' }])
})

test('slot validation rejects absent, blank, fractional and unsafe indices without reading a project', async () => {
    for (const search of ['', '?slot=', '?slot=%20', '?slot=-1', '?slot=0.5', '?slot=9007199254740992', '?slot=NaN']) {
        const app = harness()
        assert.equal((await app.get(search)).status, 400, search)
        assert.equal(app.queries(), 0)
        assert.equal(app.downloads.length, 0)
    }
})

test('slots are bounded by the actual authorized character list', async () => {
    const app = harness()
    assert.equal((await app.get('?slot=23')).status, 400)
    assert.equal(app.queries(), 1)
    assert.equal(app.downloads.length, 0)
})

test('authentication and project ownership are checked before reading any character asset', async () => {
    const unauthenticated = harness({ authenticated: false })
    assert.equal((await unauthenticated.get('?slot=22')).status, 401)
    assert.equal(unauthenticated.queries(), 0)
    const missingProject = harness({ projectPayload: null })
    assert.equal((await missingProject.get('?slot=22')).status, 404)
    assert.deepEqual(missingProject.filters, [['id', 'project-id'], ['employee_email', 'owner@example.com']])
    assert.equal(missingProject.downloads.length, 0)
})
