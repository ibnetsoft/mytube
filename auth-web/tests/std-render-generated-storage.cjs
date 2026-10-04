const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('../node_modules/typescript')

const root = path.resolve(__dirname, '..')
const gcsBucket = 'air-studio-prod'
const project = { id: 'project-owner' }

function load(relativePath, dependencies = {}, cache = new Map()) {
    const filename = path.join(root, relativePath)
    if (cache.has(filename)) return cache.get(filename)
    const exports = {}
    cache.set(filename, exports)
    const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    }).outputText
    new Function('exports', 'require', compiled)(exports, name => {
        if (name in dependencies) return dependencies[name]
        if (name === 'crypto') return require('node:crypto')
        if (name.endsWith('stdGeneratedSceneStorage') || name.endsWith('stdPolicy') || name.endsWith('stdComic')) {
            return load(`lib/${name.split('/').pop()}.ts`, dependencies, cache)
        }
        if (name.endsWith('.json')) return require(path.resolve(path.dirname(filename), name))
        // Helpers for rendering, subtitles and audio are outside asset preparation.
        return {}
    })
    return exports
}

test('scene storage resolver recognizes persisted GCS metadata and URL formats', () => {
    const { resolveGeneratedSceneStorage } = load('lib/stdGeneratedSceneStorage.ts')
    const objectPath = 'topics/3373/images/scene-024 test.png'
    const expected = { provider: 'gcs', bucket: gcsBucket, path: objectPath }
    const references = [
        { metadata: { metadata: { cowork_image_asset: { storage_provider: 'gcs', bucket: gcsBucket, object_path: objectPath } } } },
        { metadata: { cowork_image_asset: { gcs_bucket: gcsBucket, gcs_path: objectPath } } },
        { metadata: { storage_provider: 'gcs', storage_bucket: gcsBucket, storage_path: objectPath } },
        { metadata: { image_gcs_bucket: gcsBucket, image_gcs_path: objectPath } },
        { image_url: `/api/std/assets/gcs-file?${new URLSearchParams({ bucket: gcsBucket, path: objectPath })}` },
        { image_url: `gs://${gcsBucket}/${objectPath}` },
        { image_url: `https://storage.googleapis.com/${gcsBucket}/${encodeURI(objectPath)}?X-Goog-Expires=300` },
        { image_url: `https://${gcsBucket}.storage.googleapis.com/${encodeURI(objectPath)}` },
        { image_url: `https://legacy.example/storage/v1/object/public/${gcsBucket}/${encodeURI(objectPath)}` },
        { metadata: { storage_bucket: gcsBucket, storage_path: objectPath } },
    ]
    for (const scene of references) assert.deepEqual(resolveGeneratedSceneStorage(scene, 'image', gcsBucket), expected)
})

test('scene resolver prioritizes explicit GCS over stale legacy references and keeps video sources separate', () => {
    const { resolveGeneratedSceneStorage } = load('lib/stdGeneratedSceneStorage.ts')
    const scene = { metadata: {
        storage_bucket: 'content-assets', storage_path: 'legacy/image.png',
        gcs_bucket: gcsBucket, gcs_path: 'topics/3373/images/image.png',
        video_gcs_bucket: gcsBucket, video_gcs_path: 'topics/3373/videos/video.mp4',
    } }
    assert.deepEqual(resolveGeneratedSceneStorage(scene, 'image', gcsBucket), { provider: 'gcs', bucket: gcsBucket, path: 'topics/3373/images/image.png' })
    assert.deepEqual(resolveGeneratedSceneStorage(scene, 'video', gcsBucket), { provider: 'gcs', bucket: gcsBucket, path: 'topics/3373/videos/video.mp4' })
    assert.equal(resolveGeneratedSceneStorage({ metadata: { gcs_bucket: gcsBucket, gcs_path: 'topics/3373/images/image.png' } }, 'video', gcsBucket), null)
})

test('scene resolver retains genuine Supabase references and ignores unsupported media URLs', () => {
    const { resolveGeneratedSceneStorage } = load('lib/stdGeneratedSceneStorage.ts')
    assert.deepEqual(resolveGeneratedSceneStorage({ image_url: 'https://legacy.example/storage/v1/object/public/content-assets/legacy/image.png' }, 'image', gcsBucket), {
        provider: 'supabase', bucket: 'content-assets', path: 'legacy/image.png',
    })
    assert.equal(resolveGeneratedSceneStorage({ image_url: 'blob:https://studio.example/local' }, 'image', gcsBucket), null)
    assert.equal(resolveGeneratedSceneStorage({ image_url: 'https://unrelated.example/image.png' }, 'image', gcsBucket), null)
})

function gcsScene(sceneNumber, type = 'image') {
    const objectPath = `topics/3373/${type}s/scene-${sceneNumber}.${type === 'image' ? 'png' : 'mp4'}`
    return {
        id: `scene-${sceneNumber}`,
        scene_number: sceneNumber,
        metadata: {
            [`${type}_url`]: `/api/std/assets/gcs-file?${new URLSearchParams({ bucket: gcsBucket, path: objectPath })}`,
            metadata: {
                [`cowork_${type}_asset`]: {
                    storage_provider: 'gcs', bucket: gcsBucket, object_path: objectPath,
                    gcs_bucket: gcsBucket, gcs_path: objectPath,
                },
            },
        },
    }
}

function harness({ missingGcs = false, missingSupabase = false, existingRows = [] } = {}) {
    let configured = false
    const calls = []
    const records = structuredClone(existingRows)
    const db = {
        storage: {
            from(bucket) {
                return {
                    async download(objectPath) {
                        calls.push({ type: 'supabase-download', bucket, path: objectPath })
                        if (missingSupabase) return { data: null, error: { message: 'Object not found' } }
                        return { data: new Blob([Buffer.from('legacy-media')], { type: objectPath.endsWith('.mp4') ? 'video/mp4' : 'image/png' }), error: null }
                    },
                    getPublicUrl(objectPath) {
                        calls.push({ type: 'supabase-public-url', bucket, path: objectPath })
                        return { data: { publicUrl: `https://legacy.example/storage/v1/object/public/${bucket}/${objectPath}` } }
                    },
                }
            },
        },
        from(table) {
            assert.equal(table, 'std_project_assets')
            let payload, operation, id
            const query = {
                insert(row) { payload = row; operation = 'insert'; return query },
                update(row) { payload = row; operation = 'update'; return query },
                eq(field, value) {
                    if (field === 'id') id = value
                    else { assert.equal(field, 'project_id'); assert.equal(value, project.id) }
                    return query
                },
                select() { return query },
                async single() {
                    calls.push({ type: `db-${operation}`, payload: structuredClone(payload), id })
                    const index = records.findIndex(row => row.id === id)
                    const row = { ...(index >= 0 ? records[index] : {}), id: id || `asset-${records.length + 1}`, ...payload }
                    if (index >= 0) records[index] = row
                    else records.push(row)
                    return { data: row, error: null }
                },
            }
            return query
        },
    }
    const gcs = {
        gcsBucketName: () => gcsBucket,
        isGcsStorageConfigured: () => configured,
        async isGcsConfiguredAsync() { calls.push({ type: 'gcs-config' }); configured = true; return true },
        async getGcsObjectMetadata(input) {
            assert.equal(configured, true, 'load database credentials before checking a GCS object')
            calls.push({ type: 'gcs-metadata', ...input })
            if (missingGcs) throw new Error('GCS object not found')
            return { size: 4096, contentType: input.objectPath.endsWith('.mp4') ? 'video/mp4' : 'image/png' }
        },
        async downloadGcsObject() { throw new Error('Existing GCS media must not be downloaded for re-upload') },
        async uploadGcsBuffer(input) {
            assert.equal(configured, true)
            assert.equal((input.buffer || input.data).toString(), 'legacy-media')
            calls.push({ type: 'gcs-upload', path: input.objectPath, contentType: input.contentType })
            return { provider: 'gcs', bucket: gcsBucket, path: input.objectPath }
        },
    }
    const queue = load('lib/stdRenderQueue.ts', {
        './supabaseAdmin': { supabaseAdmin: db }, './gcsStorage': gcs,
    })
    return { prepare: queue.ensureStdGeneratedSceneAssetsArchived, calls, records }
}

for (const [sceneNumber, type] of [[24, 'image'], [1, 'video']]) {
    test(`existing GCS ${type} registers its original reference without Supabase reads or re-upload`, async () => {
        const h = harness()
        const scene = gcsScene(sceneNumber, type)
        const result = await h.prepare(project, [scene], [])
        assert.equal(result.length, 1)
        const asset = result[0]
        assert.equal(asset.scene_number, sceneNumber)
        assert.equal(asset.scene_id, scene.id)
        assert.equal(asset.asset_type, type)
        assert.equal(asset.file_size, 4096)
        assert.equal(asset.mime_type, type === 'video' ? 'video/mp4' : 'image/png')
        assert.equal(asset.metadata.storage_provider, 'gcs')
        assert.equal(asset.metadata.gcs_bucket, gcsBucket)
        assert.equal(asset.metadata.gcs_path, scene.metadata.metadata[`cowork_${type}_asset`].object_path)
        assert.equal(asset.metadata.storage_bucket, gcsBucket)
        assert.equal(asset.metadata.storage_path, asset.metadata.gcs_path)
        assert.equal(h.calls.some(call => call.type.startsWith('supabase-')), false)
        assert.equal(h.calls.some(call => call.type === 'gcs-upload'), false)
        assert.equal(h.calls.filter(call => call.type === 'gcs-metadata').length, 1)
        assert.ok(h.calls.findIndex(call => call.type === 'gcs-metadata') < h.calls.findIndex(call => call.type === 'db-insert'))
    })
}

test('cold database GCS configuration is loaded before recovering the first video', async () => {
    const h = harness()
    await h.prepare(project, [gcsScene(1, 'video')], [])
    const configureIndex = h.calls.findIndex(call => call.type === 'gcs-config')
    const metadataIndex = h.calls.findIndex(call => call.type === 'gcs-metadata')
    assert.ok(configureIndex >= 0 && configureIndex < metadataIndex)
})

for (const [sceneNumber, type] of [[24, 'image'], [1, 'video']]) {
    test(`missing GCS ${type} fails without registration or Supabase fallback`, async () => {
        const h = harness({ missingGcs: true })
        await assert.rejects(h.prepare(project, [gcsScene(sceneNumber, type)], []), /GCS|gcs/)
        assert.equal(h.calls.some(call => call.type.startsWith('db-')), false)
        assert.equal(h.calls.some(call => call.type.startsWith('supabase-')), false)
        assert.equal(h.calls.some(call => call.type === 'gcs-upload'), false)
    })
}

for (const [sceneNumber, type] of [[24, 'image'], [1, 'video']]) {
    test(`legacy Supabase ${type} is copied to GCS before the asset is registered`, async () => {
        const h = harness()
        const objectPath = `legacy/scene-${sceneNumber}.${type === 'video' ? 'mp4' : 'png'}`
        const scene = { scene_number: sceneNumber, metadata: { [`cowork_${type}_asset`]: { bucket: 'content-assets', object_path: objectPath } } }
        const result = await h.prepare(project, [scene], [])
        assert.equal(result[0].metadata.gcs_bucket, gcsBucket)
        assert.equal(result[0].metadata.gcs_path, objectPath)
        assert.equal(h.calls.filter(call => call.type === 'supabase-download').length, 1)
        assert.equal(h.calls.filter(call => call.type === 'gcs-upload').length, 1)
        assert.ok(h.calls.findIndex(call => call.type === 'gcs-upload') < h.calls.findIndex(call => call.type === 'db-insert'))
    })
}

test('failed legacy download never registers an unusable asset', async () => {
    const h = harness({ missingSupabase: true })
    const scene = { scene_number: 24, metadata: { storage_bucket: 'content-assets', storage_path: 'legacy/missing.png' } }
    await assert.rejects(h.prepare(project, [scene], []))
    assert.equal(h.calls.some(call => call.type === 'gcs-upload' || call.type.startsWith('db-')), false)
})

test('user-uploaded active GCS media is preserved over generated scene metadata', async () => {
    const asset = {
        id: 'user-image', scene_number: 24, asset_type: 'image', status: 'uploaded',
        metadata: { storage_provider: 'gcs', storage_bucket: gcsBucket, storage_path: 'std-projects/project-owner/custom-image.png', custom: 'keep' },
    }
    const h = harness({ existingRows: [asset] })
    const result = await h.prepare(project, [gcsScene(24)], [asset])
    assert.deepEqual(result, [asset])
    assert.equal(h.calls.some(call => call.type === 'gcs-metadata' || call.type.startsWith('db-') || call.type.startsWith('supabase-')), false)
})

test('repeated preparation reuses the registered GCS asset without another storage check or write', async () => {
    const h = harness()
    const scene = gcsScene(24)
    const first = await h.prepare(project, [scene], [])
    const metadataCount = h.calls.filter(call => call.type === 'gcs-metadata').length
    const writes = h.calls.filter(call => call.type.startsWith('db-')).length
    const second = await h.prepare(project, [scene], first)
    assert.deepEqual(second, first)
    assert.equal(h.calls.filter(call => call.type === 'gcs-metadata').length, metadataCount)
    assert.equal(h.calls.filter(call => call.type.startsWith('db-')).length, writes)
})

test('recovering a legacy asset updates its existing row and retains unrelated metadata', async () => {
    const asset = {
        id: 'legacy-asset', scene_number: 24, asset_type: 'image', status: 'assigned',
        metadata: { storage_bucket: 'content-assets', storage_path: 'legacy/still.png', review_note: 'keep' },
    }
    const h = harness({ existingRows: [asset] })
    const result = await h.prepare(project, [gcsScene(24)], [asset])
    assert.equal(result.length, 1)
    assert.equal(result[0].id, asset.id)
    assert.equal(result[0].metadata.review_note, 'keep')
    assert.equal(result[0].metadata.gcs_bucket, gcsBucket)
    assert.equal(h.calls.filter(call => call.type === 'db-update').length, 1)
    assert.equal(h.calls.some(call => call.type === 'db-insert'), false)
})
