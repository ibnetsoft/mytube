const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const source = fs.readFileSync(path.join(__dirname, '../lib/stdSceneMediaUrl.ts'), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
const exported = {}
new Function('exports', compiled)(exported)

assert.equal(
    exported.sceneImageUrl({
        image_url: '/api/std/assets/gcs-file?bucket=air-studio-prod&path=topics%2F3373%2Fimages%2Fscene-096.png',
        metadata: { cowork_image_asset: { storage_provider: 'gcs', bucket: 'air-studio-prod', object_path: 'topics/3373/images/scene-096.png' } },
    }),
    '/api/std/assets/gcs-file?bucket=air-studio-prod&path=topics%2F3373%2Fimages%2Fscene-096.png',
)
assert.equal(
    exported.sceneImageUrl({ metadata: { cowork_image_asset: { storage_provider: 'gcs', gcs_bucket: 'air-studio-prod', gcs_path: 'topics/3373/images/scene-094.png' } } }),
    '/api/std/assets/gcs-file?bucket=air-studio-prod&path=topics%2F3373%2Fimages%2Fscene-094.png',
)
assert.equal(
    exported.sceneImageUrl({ image_url: 'https://giorysjpgxzdypbmxwmx.supabase.co/storage/v1/object/public/air-studio-prod/topics/3373/images/scene-001-hash.png' }),
    '/api/std/assets/gcs-file?bucket=air-studio-prod&path=topics%2F3373%2Fimages%2Fscene-001-hash.png',
)
assert.equal(
    exported.sceneImageUrl({
        image_url: 'https://giorysjpgxzdypbmxwmx.supabase.co/storage/v1/object/public/air-studio-prod/topics/3373/images/scene-002-hash.png',
        metadata: { storage_provider: 'gcs', storage_bucket: 'air-studio-prod', storage_path: 'topics/3373/images/scene-002-hash.png' },
    }),
    '/api/std/assets/gcs-file?bucket=air-studio-prod&path=topics%2F3373%2Fimages%2Fscene-002-hash.png',
)
assert.equal(
    exported.sceneImageUrl({ image_url: 'https://example.supabase.co/storage/v1/object/public/air-studio-prod/other/photo.png' }),
    'https://example.supabase.co/storage/v1/object/public/air-studio-prod/other/photo.png',
)
assert.equal(
    exported.sceneImageUrl({ metadata: { cowork_image_asset: { bucket: 'content-assets', object_path: 'legacy/photo.png' } } }),
    '',
)
assert.equal(
    exported.sceneImageUrl({ image_url: 'https://example.com/scene.png' }),
    'https://example.com/scene.png',
)
console.log('PASS: GCS scene images use authenticated proxy while legacy and direct URLs remain intact')
