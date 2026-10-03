const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')

const filename = path.resolve(__dirname, '../lib/stdVoiceStudio.ts')
const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
}).outputText
const audio = Buffer.alloc(400, 7)
const input = { text: '同じ声で読みます。', voiceId: 'gemini:Achernar', direction: 'Calm narration', speed: 1, language: 'ja-JP' }
function googleError(httpStatus, status, message = 'Provider error', reason, url = 'https://texttospeech.googleapis.com/v1/text:synthesize') {
    return { response: { status: httpStatus, config: { url }, data: { error: {
        code: httpStatus, status, message,
        details: reason ? [{ '@type': 'type.googleapis.com/google.rpc.ErrorInfo', reason }] : [],
    } } } }
}
function harness(handler, options = {}) {
    let clock = 0
    const files = options.files || new Map()
    const calls = [], sleeps = []
    const sandbox = { exports: {}, Buffer, URL, process: { env: { VOICE_STUDIO_CLOUD_PROJECT: 'test-project' } },
        Date: class extends Date { static now() { return clock } },
        setTimeout(callback, delay) { sleeps.push(delay); clock += delay; callback() },
        require(id) {
            if (id === './voiceStudioAuth') return { voiceStudioAuth: async () => ({ request: async config => {
                calls.push(config)
                return handler(config, calls.length, ms => { clock += ms })
            } }) }
            if (id === './voiceStudioCatalog') return { voiceStudioName: value => value.replace('gemini:', '') }
            if (id === 'fs/promises') return {
                readFile: async key => { if (!files.has(key)) throw new Error('ENOENT'); return files.get(key) },
                mkdir: async () => {},
                writeFile: async (key, data) => { if (options.writeError) throw options.writeError; files.set(key, data) },
                rename: async (from, to) => { files.set(to, files.get(from)); files.delete(from) },
            }
            return require(id)
        },
    }
    vm.runInNewContext(compiled, sandbox, { filename })
    return { generate: sandbox.exports.generateVoiceStudioMp3, CloudError: sandbox.exports.VoiceStudioCloudError, calls, sleeps, files, now: () => clock }
}
async function main() {
    const retry = harness((config, call) => {
        if (call === 1) throw googleError(500, 'INTERNAL', 'An internal error occurred.')
        return { data: { audioContent: audio.toString('base64') } }
    })
    const [first, second] = await Promise.all([retry.generate(input), retry.generate(input)])
    assert.deepEqual(first, audio)
    assert.deepEqual(second, audio)
    assert.equal(retry.calls.length, 2)
    assert.equal(retry.calls[0].data, retry.calls[1].data)
    assert.equal(retry.calls[0].data.voice.name, 'Achernar')
    assert.equal(retry.calls[0].data.voice.languageCode, 'ja-JP')
    assert.equal(retry.calls[0].data.input.text, input.text)
    assert.equal(retry.calls[0].retry, false)
    assert.deepEqual(retry.sleeps, [1000])
    assert.deepEqual(retry.calls.map(call => call.timeout), [180000, 179000])
    await retry.generate(input)
    assert.equal(retry.calls.length, 2)
    const reopened = harness(() => { throw new Error('Cache miss must not call Google') }, { files: retry.files })
    assert.deepEqual(await reopened.generate(input), audio)
    assert.equal(reopened.calls.length, 0)
    console.log('PASS: one transient retry keeps voice/text/body, deduplicates concurrent calls, and preserves disk cache')

    for (const [httpStatus, status] of [[503, 'UNAVAILABLE'], [429, 'RESOURCE_EXHAUSTED']]) {
        const exhausted = harness(() => { throw googleError(httpStatus, status) })
        await assert.rejects(exhausted.generate(input), error => {
            assert.equal(error.name, 'VoiceStudioCloudError')
            assert.equal(error.noAudioProduced, true)
            assert.equal(error.httpStatus, httpStatus)
            assert.equal(error.status, status)
            assert.ok(!error.message.includes('결제'))
            return true
        })
        assert.equal(exhausted.calls.length, 3)
        assert.deepEqual(exhausted.sleeps, [1000, 2000])
        assert.deepEqual(exhausted.calls.map(call => call.timeout), [180000, 179000, 177000])
    }
    console.log('PASS: structured 503/429 stop after three attempts within one request budget')

    const forbidden = harness(() => { throw googleError(403, 'PERMISSION_DENIED', 'Permission denied. Bearer secret-access-token https://example.test/?token=private {"access_token":"short-secret"}', 'IAM_PERMISSION_DENIED') })
    await assert.rejects(forbidden.generate(input), error => {
        assert.equal(error.noAudioProduced, true)
        assert.equal(error.reason, 'IAM_PERMISSION_DENIED')
        assert.match(error.message, /인증 또는 API 사용 권한/)
        assert.match(error.providerMessage, /Permission denied/)
        assert.ok(!error.message.includes('secret-access-token'))
        assert.ok(!error.message.includes('token=private'))
        assert.ok(!error.message.includes('short-secret'))
        assert.equal(error.config, undefined)
        assert.equal(error.response, undefined)
        return true
    })
    assert.equal(forbidden.calls.length, 1)
    const auth = harness(() => { throw googleError(503, 'UNAVAILABLE', 'Token service unavailable', undefined, 'https://sts.googleapis.com/v1/token') })
    await assert.rejects(auth.generate(input), error => error.stage === 'authentication' && /Google 인증 서버/.test(error.message))
    console.log('PASS: permission failure does not retry; safe error details and authentication stage remain distinguishable')

    for (const [status, message, reason] of [
        ['INTERNAL', 'Content blocked by safety filters', undefined],
        ['INTERNAL', "Input text or prompt violates Vertex AI's usage guidelines", undefined],
        ['INTERNAL', 'Unable to synthesize audio. Support codes: 12345678', undefined],
        ['FAILED_PRECONDITION', 'Billing account disabled', 'BILLING_DISABLED'],
        ['INVALID_ARGUMENT', 'Invalid synthesis settings', undefined],
    ]) {
        const terminal = harness(() => { throw googleError(500, status, message, reason) })
        await assert.rejects(terminal.generate(input), error => error.noAudioProduced === true)
        assert.equal(terminal.calls.length, 1)
        assert.deepEqual(terminal.sleeps, [])
    }
    console.log('PASS: safety, billing, and invalid-request rejections never retry even with HTTP 500')

    for (const failure of [
        { code: 'ETIMEDOUT', message: 'Transport timed out' },
        { response: { status: 500, data: '<html>Proxy failure</html>' } },
        { response: { status: 503, data: { audioContent: audio.toString('base64'), error: { code: 503, status: 'UNAVAILABLE' } } } },
        googleError(504, 'DEADLINE_EXCEEDED'),
        googleError(408, 'DEADLINE_EXCEEDED'),
        googleError(499, 'CANCELLED'),
        googleError(500, 'DEADLINE_EXCEEDED'),
    ]) {
        const uncertain = harness(() => { throw failure })
        await assert.rejects(uncertain.generate(input), error => error.noAudioProduced === false)
        assert.equal(uncertain.calls.length, 1)
        assert.deepEqual(uncertain.sleeps, [])
    }
    const malformed = harness(() => ({ data: { audioContent: 'AA==' } }))
    await assert.rejects(malformed.generate(input), error => error.noAudioProduced === false)
    assert.equal(malformed.calls.length, 1)
    const persistence = harness(() => ({ data: { audioContent: audio.toString('base64') } }), { writeError: new Error('Disk persistence failed') })
    await assert.rejects(persistence.generate(input), error => error.message === 'Disk persistence failed' && error.noAudioProduced !== true)
    console.log('PASS: transport uncertainty, malformed audio, and cache persistence failures never authorize claim release')

    const deadline = harness((config, call, advance) => {
        advance(call === 1 ? 100000 : 78000)
        throw googleError(500, 'INTERNAL')
    })
    await assert.rejects(deadline.generate(input), error => error.noAudioProduced === true)
    assert.equal(deadline.calls.length, 2)
    assert.deepEqual(deadline.calls.map(call => call.timeout), [180000, 79000])
    assert.equal(deadline.now(), 179000)
    assert.deepEqual(deadline.sleeps, [1000])
    console.log('PASS: time spent in failed requests reduces later timeouts and stops retries before the 180-second deadline')
}
main().catch(error => { console.error(error); process.exitCode = 1 })
