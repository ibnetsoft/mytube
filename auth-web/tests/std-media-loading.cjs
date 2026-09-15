const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const ts = require('typescript')

const filename = path.resolve(__dirname, '../lib/stdMediaLoading.ts')
const mod = new Module(filename, module)
mod.filename = filename
mod.paths = Module._nodeModulePaths(path.dirname(filename))
mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename)

const { prioritizedSceneNumbers, selectFallbackAssetsForScenes } = mod.exports
assert.deepEqual(prioritizedSceneNumbers(1, 53), [1, 2, 3, 4])
assert.deepEqual(prioritizedSceneNumbers(10, 53), [10, 11, 12, 13])
assert.deepEqual(prioritizedSceneNumbers(52, 53), [52, 53])

const assets = [
    { id: 'scene-1-drive', status: 'uploaded', asset_type: 'video', scene_number: 1 },
    { id: 'scene-2-storage', status: 'uploaded', asset_type: 'video', scene_number: 2, metadata: { storage_public_url: 'https://storage/2' } },
    { id: 'scene-8-drive', status: 'assigned', asset_type: 'image', scene_number: 8 },
    { id: 'audio-drive', status: 'uploaded', asset_type: 'audio' },
]
assert.deepEqual(
    selectFallbackAssetsForScenes(assets, [1, 2, 3, 4], true).map(asset => asset.id),
    ['scene-1-drive', 'audio-drive'],
)
assert.deepEqual(selectFallbackAssetsForScenes(assets, [8], false).map(asset => asset.id), ['scene-8-drive'])
console.log('PASS: media loader prioritizes current scenes and skips direct Storage assets')
