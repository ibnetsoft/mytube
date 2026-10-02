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

const sceneMediaUrl = load('lib/stdSceneMediaUrl.ts')

async function getHydratedScenes(scenes, sourceScenes = []) {
    const project = {
        id: 'e9233112-f0d7-4b35-91bf-2f892844eb30',
        employee_email: 'owner@example.com',
        topic_queue_id: 3373,
        project_payload: {},
        source_payload: { pregenerated_script: 'Narration' },
    }
    const records = {
        std_projects: project,
        std_project_scenes: scenes,
        std_project_assets: [],
        topics_queue: { pregenerated_structure: { scenes: sourceScenes } },
    }
    const supabaseAdmin = {
        from(table) {
            const result = { data: records[table], error: null }
            const query = {
                select: () => query,
                eq: () => query,
                in: () => query,
                order: () => query,
                maybeSingle: async () => result,
                then: (resolve, reject) => Promise.resolve(result).then(resolve, reject),
            }
            return query
        },
        storage: {
            from: bucket => ({
                getPublicUrl: objectPath => ({
                    data: { publicUrl: `https://storage.example/storage/v1/object/public/${bucket}/${objectPath}` },
                }),
            }),
        },
    }
    const route = load('app/api/std/projects/[projectId]/route.ts', {
        'next/server': { NextResponse: Response },
        '@/lib/stdComic': {},
        '@/lib/stdProjectEditPolicy': {},
        '@/lib/stdThumbnailRender': {},
        '@/lib/supabaseAdmin': { supabaseAdmin },
        '@/lib/stdWeb': { requireStdUser: async () => ({ ok: true, requester: { email: project.employee_email } }) },
        '@/lib/stdPolicy': {},
        '@/lib/stdRenderQueue': { getStdProjectRenderHistory: async () => [] },
        '@/lib/stdCharacterProtection': { protectCharacterReferenceUrls: value => value },
        '@/lib/gcsStorage': { isGcsConfiguredAsync: async () => false },
        '@/lib/stdSceneMediaUrl': sceneMediaUrl,
    })
    const response = await route.GET(new Request(`https://studio.example/api/std/projects/${project.id}`), {
        params: { projectId: project.id },
    })
    assert.equal(response.status, 200)
    return (await response.json()).scenes
}

function gcsScene(sceneNumber) {
    const objectPath = `topics/3373/images/scene-${String(sceneNumber).padStart(3, '0')}-hash.png`
    const imageUrl = `/api/std/assets/gcs-file?${new URLSearchParams({ bucket: 'air-studio-prod', path: objectPath })}`
    return {
        scene_number: sceneNumber,
        metadata: {
            image_url: imageUrl,
            metadata: {
                cowork_image_asset: {
                    storage_provider: 'gcs',
                    bucket: 'air-studio-prod',
                    gcs_bucket: 'air-studio-prod',
                    object_path: objectPath,
                    gcs_path: objectPath,
                },
            },
        },
    }
}

test('project hydration preserves existing GCS proxy posters with nested cowork metadata and no image assets', async () => {
    const scenes = [1, 2, 3, 4].map(gcsScene)
    const hydrated = await getHydratedScenes(scenes)
    assert.deepEqual(hydrated.map(scene => scene.image_url), scenes.map(scene => scene.metadata.image_url))
})

test('project hydration preserves a GCS proxy poster inherited from its source topic', async () => {
    const sourceScene = gcsScene(2)
    const hydrated = await getHydratedScenes([{ scene_number: 2, metadata: {} }], [sourceScene])
    assert.equal(hydrated[0].image_url, sourceScene.metadata.image_url)
})

test('project hydration retains legitimate Supabase public scene images', async () => {
    const imageUrl = 'https://storage.example/storage/v1/object/public/content-assets/projects/project/image.png'
    const hydrated = await getHydratedScenes([{ scene_number: 1, metadata: { image_url: imageUrl } }])
    assert.equal(hydrated[0].image_url, imageUrl)
})
