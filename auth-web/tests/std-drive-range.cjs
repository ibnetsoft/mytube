const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const ts = require('typescript')

const filename = path.resolve(__dirname, '../lib/stdGoogleDrive.ts')
const mod = new Module(filename, module)
mod.filename = filename
mod.paths = Module._nodeModulePaths(path.dirname(filename))
const originalRequire = mod.require.bind(mod)
mod.require = id => id === './googleDriveConfig'
    ? { getGoogleDriveAccessToken: async () => 'token', getGoogleDriveConfig: async () => ({ rootFolderId: 'root' }) }
    : originalRequire(id)
mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename)

async function main() {
    const originalFetch = global.fetch
    let requestHeaders
    global.fetch = async (_url, options) => {
        requestHeaders = options.headers
        return new Response(Buffer.from('chunk'), {
            status: 206,
            headers: {
                'content-range': 'bytes 0-4/100',
                'content-length': '5',
                'content-type': 'video/mp4',
            },
        })
    }
    try {
        const result = await mod.exports.downloadStdDriveFileChunk('file-id', 'bytes=0-4')
        assert.equal(requestHeaders.Range, 'bytes=0-4')
        assert.equal(result.status, 206)
        assert.equal(result.contentRange, 'bytes 0-4/100')
        assert.equal(result.buffer.toString(), 'chunk')
    } finally {
        global.fetch = originalFetch
    }
    console.log('PASS: Drive media requests forward byte ranges for streaming playback')
}

main().catch(error => {
    console.error(error)
    process.exitCode = 1
})
