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

function harness({ projectPayload = payload, authenticated = true, imageBytes = new Uint8Array([1, 2, 3]), registry = null } = {}) {
    const filters = []
    const downloads = []
    let queries = 0
    const query = {
        select: () => query,
        eq: (key, value) => { filters.push([key, value]); return query },
        order: () => query, limit: () => query,
        maybeSingle: async () => ({ data: projectPayload ? { project_payload: projectPayload, ...(registry ? { topic_queue_id: 42 } : {}) } : null, error: null }),
    }
    const route = load('app/api/std/projects/[projectId]/character-thumbnail/route.ts', {
        'next/server': { NextResponse: Response },
        '@/lib/supabaseAdmin': { supabaseAdmin: { from: table => {
            queries += 1
            if (table !== 'topic_character_assets') return query
            const reference = { select: () => reference, eq: () => reference, order: () => reference,
                limit: () => reference, maybeSingle: async () => ({ data: registry, error: null }) }
            return reference
        } } },
        '@/lib/stdWeb': {
            requireStdUser: async () => authenticated
                ? { ok: true, requester: { email: 'owner@example.com' } }
                : { ok: false, response: new Response(null, { status: 401 }) },
        },
        '@/lib/stdCharacterProtection': characterProtection,
        '@/lib/stdCharacterThumbnail': characterThumbnail,
        'sharp': { default: require('sharp') },
        '@/lib/gcsStorage': {
            getGcsConfig: async () => ({}),
            gcsBucketName: () => 'studio-assets',
            downloadGcsObject: async object => { downloads.push(object); return imageBytes },
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

test('prepared-topic and nested recurring-character paths are accepted', async () => {
    const preparedCharacter = { name: 'Prepared', image_url: '/api/std/assets/gcs-file?bucket=studio-assets&path=topics%2Fprepared%2FBp8mgsjeeEo%2Fcharacters%2Fprepared.png' }
    const prepared = harness({ projectPayload: { structure: { main_character: preparedCharacter } } })
    assert.equal((await prepared.get('?slot=0')).status, 200)
    assert.deepEqual(prepared.downloads, [{ bucket: 'studio-assets', objectPath: 'topics/prepared/Bp8mgsjeeEo/characters/prepared.png' }])

    const nestedCharacter = { name: 'Nested', image_url: '/api/std/assets/gcs-file?bucket=studio-assets&path=topics%2F3377%2Fcharacters%2Frecurring-character-designs%2Fnested.webp' }
    const nested = harness({ projectPayload: { structure: { main_character: nestedCharacter } } })
    assert.equal((await nested.get('?slot=0')).status, 200)
    assert.deepEqual(nested.downloads, [{ bucket: 'studio-assets', objectPath: 'topics/3377/characters/recurring-character-designs/nested.webp' }])
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

test('model sheets are reduced to small WebP images without cropping or exposing originals', async () => {
    const sharp = require('sharp')
    const imageBytes = await sharp({ create: { width: 2048, height: 1152, channels: 3, background: '#557766' } }).png().toBuffer()
    const character = { name: 'Lead', character_key: 'lead', image_url: '/portrait.png', character_sheet_assets: [{
        type: 'model_sheet', status: 'ready', profile: 'turnaround', fingerprint: 'version-one',
        image_url: '/api/std/assets/gcs-file?bucket=studio-assets&path=topics/42/characters/lead/sheets/model.png',
        gcs_bucket: 'studio-assets', gcs_path: 'topics/42/characters/lead/sheets/model.png',
    }] }
    const projectPayload = { structure: { main_character: character } }
    const app = harness({ projectPayload, imageBytes })
    const response = await app.get('?slot=0&sheet=model_sheet&preview=1')
    assert.equal(response.status, 200)
    assert.equal(response.headers.get('content-type'), 'image/webp')
    const result = await sharp(Buffer.from(await response.arrayBuffer())).metadata()
    assert.equal(result.width, 160)
    assert.equal(result.height, 90)
    const safe = characterProtection.protectCharacterReferenceUrls(projectPayload, 'project-id')
    const sheet = safe.structure.main_character.character_sheet_assets[0]
    assert.match(sheet.image_url, /slot=0&sheet=model_sheet&v=version-one/)
    assert.equal(sheet.gcs_path, undefined)
    assert.equal(projectPayload.structure.main_character.character_sheet_assets[0].gcs_path, character.character_sheet_assets[0].gcs_path)
    const restored = harness({ projectPayload: safe, imageBytes, registry: {
        image_url: character.image_url, usage_context: { character_design: character },
    } })
    assert.equal((await restored.get('?slot=0&sheet=model_sheet')).status, 200)
    assert.equal(restored.downloads[0].objectPath, 'topics/42/characters/lead/sheets/model.png')
    const denied = harness({ projectPayload, authenticated: false, imageBytes })
    assert.equal((await denied.get('?slot=0&sheet=model_sheet')).status, 401)
    assert.equal(denied.downloads.length, 0)
    assert.equal((await app.get('?slot=0&sheet=../../other')).status, 400)
    assert.equal((await app.get('?slot=0&sheet=lipsync')).status, 404)
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

test('expanded previews preserve authorization and request an uncropped larger image', async () => {
    const originalFetch = global.fetch
    const urls = []
    global.fetch = async url => { urls.push(new URL(url)); return new Response(new Uint8Array([1]), { headers: { 'content-type': 'image/webp' } }) }
    try {
        const app = harness({ projectPayload: { main_character: { name: 'Portrait', image_url: 'https://example.supabase.co/storage/v1/object/public/images/portrait.png' } } })
        assert.equal((await app.get('?slot=0')).status, 200)
        assert.equal((await app.get('?slot=0&preview=1')).status, 200)
        assert.equal(urls[0].searchParams.get('width'), '64')
        assert.equal(urls[1].searchParams.get('width'), '1024')
        assert.equal(urls[1].searchParams.get('resize'), 'contain')
        assert(app.filters.some(([key, value]) => key === 'employee_email' && value === 'owner@example.com'))
        const denied = harness({ authenticated: false })
        assert.equal((await denied.get('?slot=0&preview=1')).status, 401)
        assert.equal(urls.length, 2)
    } finally { global.fetch = originalFetch }
})
