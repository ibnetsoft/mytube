const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')

const source = fs.readFileSync(path.join(__dirname, '../lib/stdAeSceneDelivery.ts'), 'utf8')
const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const delivery = {}
new Function('exports', compiled)(delivery)

assert.equal(delivery.parseClaimAeSceneDelivery(''), undefined)
assert.equal(delivery.parseClaimAeSceneDelivery('{"ae_scene_delivery":"gcs"}'), 'gcs')
assert.throws(() => delivery.parseClaimAeSceneDelivery('{bad json'), /Invalid request body/)
assert.throws(() => delivery.parseClaimAeSceneDelivery('{"ae_scene_delivery":"remote"}'), /Invalid AE scene delivery/)
assert.throws(() => delivery.parseClaimAeSceneDelivery('{"ae_scene_delivery":null}'), /Invalid AE scene delivery/)

const legacy = { scenes: [{ metadata: { ae_motion_asset: {
    status: 'ready', storage_provider: 'gcs', gcs_path: 'projects/1/scene.mp4',
} } }] }
assert.equal(delivery.resolveClaimAeSceneDelivery(legacy), 'gcs')
assert.equal(delivery.resolveClaimAeSceneDelivery(legacy, 'local'), 'local')
assert.equal(delivery.resolveClaimAeSceneDelivery({ ...legacy, ae_scene_delivery: 'local' }), 'local')
assert.equal(delivery.resolveClaimAeSceneDelivery({ scenes: [] }), 'local')
console.log('PASS: claim AE scene delivery selection, validation, and legacy GCS fallback')
