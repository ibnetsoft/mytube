const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')
const identity = require('./load-ts-module.cjs')('lib/stdContentIdentity.ts')

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

async function getHydratedScenes(scenes, sourceScenes = [], options = {}) {
    const project = {
        id: 'e9233112-f0d7-4b35-91bf-2f892844eb30',
        employee_email: 'owner@example.com',
        topic_queue_id: 3373,
        project_payload: options.strict ? { strict_content_identity: true, script: 'new narration' } : {},
        source_payload: { pregenerated_script: 'Narration' },
    }
    const records = {
        std_projects: project,
        std_project_scenes: scenes,
        std_project_assets: options.assets || [],
        topics_queue: { pregenerated_structure: { scenes: sourceScenes } },
    }
    const supabaseAdmin = {
        rpc: async (name) => name === 'std_project_read_fingerprint'
            ? { data: { version: 'v1', employee_email: project.employee_email }, error: null }
            : name === 'std_user_web_project' ? { data: project, error: null }
            : name === 'std_user_web_topic_structure' ? { data: records.topics_queue.pregenerated_structure, error: null }
            : { data: null, error: null },
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
        '@/lib/stdAudioAnchors': {},
        '@/lib/stdContentIdentity': identity,
        '@/lib/stdProjectReadCache': { projectReadCacheKey: () => 'key', readProjectResponse: async () => null, cacheProjectResponse: async () => {} },
        '@/lib/stdProjectAssets': { loadStdProjectAssets: async () => ({ data: records.std_project_assets, error: null }) },
        '@/lib/stdSubtitleSpeakerProgress': {},
        '@/lib/stdTemplateOverlayPng': {},
        '@/lib/stdDialogueSceneIndex': {},
        '@/lib/stdSubtitleFragments': {},
        '@/lib/stdSubtitleSaveContext': {},
        '@/lib/stdSubtitleSceneIntegrity': {},
        '@/lib/stdMotionStudio': {},
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
        '@/lib/stdUserWebPayload': { stripPostworkDirection: value => value },
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

test('strict revision never hydrates media from the prior topic or legacy scene assets', async () => {
    const sourceScene = gcsScene(2)
    const legacyAsset = { asset_type:'image', scene_number:2, metadata:{ storage_public_url:'https://storage.example/old.png' } }
    const hydrated = await getHydratedScenes([{ scene_number:2, metadata:{} }], [sourceScene], { strict:true, assets:[legacyAsset] })
    assert.equal(hydrated[0].image_url, undefined)
})

test('strict revision hydrates an asset carrying the matching script identity', async () => {
    const hash = identity.projectContentIdentity({id:'p',topic_queue_id:3373,project_payload:{script:'new narration'}}).script_sha256
    const current = { asset_type:'image', scene_number:2, metadata:{ content_identity:{script_sha256:hash}, storage_public_url:'https://storage.example/current.png' } }
    const hydrated = await getHydratedScenes([{ scene_number:2, metadata:{} }], [gcsScene(2)], { strict:true, assets:[current] })
    assert.equal(hydrated[0].image_url, 'https://storage.example/current.png')
})

test('strict scene saves strip stale direct and nested media references', () => {
    const file = fs.readFileSync(path.resolve(__dirname, '../app/api/std/projects/[projectId]/route.ts'), 'utf8')
    const ast = ts.createSourceFile('route.ts', file, ts.ScriptTarget.Latest, true)
    const fn = ast.statements.find(s => ts.isFunctionDeclaration(s) && s.name?.text === 'withoutSceneMedia')
    assert(fn)
    const code = ts.transpileModule(`${fn.getText(ast)}\nreturn withoutSceneMedia`, {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText
    const strip = new Function(code)()
    const result = strip({scene_text:'new', image_url:'old', metadata:{image_url:'old',bucket:'old',object_path:'old',metadata:{video_url:'old',gcs_path:'old',label:'keep'}}})
    assert.deepEqual(result,{scene_text:'new',metadata:{metadata:{label:'keep'}}})
})

test('project hydration retains legitimate Supabase public scene images', async () => {
    const imageUrl = 'https://storage.example/storage/v1/object/public/content-assets/projects/project/image.png'
    const hydrated = await getHydratedScenes([{ scene_number: 1, metadata: { image_url: imageUrl } }])
    assert.equal(hydrated[0].image_url, imageUrl)
})
