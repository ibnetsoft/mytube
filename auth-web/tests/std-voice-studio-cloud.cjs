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
    const calls = [], sleeps = [], startTimes = [], timers = []
    let ticking = false
    function schedule(callback, delay, record = true) {
        if (record) sleeps.push(delay)
        timers.push({ at: clock + delay, callback })
        if (!ticking) {
            ticking = true
            setImmediate(tick)
        }
    }
    function tick() {
        timers.sort((a, b) => a.at - b.at)
        const timer = timers.shift()
        clock = Math.max(clock, timer.at)
        timer.callback()
        if (timers.length) setImmediate(tick)
        else ticking = false
    }
    const sandbox = { exports: {}, Buffer, URL, process: { env: { VOICE_STUDIO_CLOUD_PROJECT: 'test-project' } },
        Date: class extends Date { static now() { return clock } },
        setTimeout: schedule,
        require(id) {
            if (id === './voiceStudioAuth') return { voiceStudioAuth: async () => ({ request: async config => {
                calls.push(config)
                startTimes.push(clock)
                return handler(config, calls.length, ms => { clock += ms },
                    (ms, value) => new Promise(resolve => schedule(() => resolve(value), ms, false)))
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
    return { generate: sandbox.exports.generateVoiceStudioMp3, CloudError: sandbox.exports.VoiceStudioCloudError, calls, sleeps, files, startTimes, now: () => clock }
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
    assert.deepEqual(retry.sleeps, [2000])
    assert.deepEqual(retry.calls.map(call => call.timeout), [180000, 178000])
    await retry.generate(input)
    assert.equal(retry.calls.length, 2)
    const reopened = harness(() => { throw new Error('Cache miss must not call Google') }, { files: retry.files })
    assert.deepEqual(await reopened.generate(input), audio)
    assert.equal(reopened.calls.length, 0)
    assert.deepEqual(reopened.sleeps, [])
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
        assert.deepEqual(exhausted.sleeps, httpStatus === 429 ? [30000, 60000] : [2000, 2000])
        assert.deepEqual(exhausted.calls.map(call => call.timeout), httpStatus === 429
            ? [180000, 150000, 90000] : [180000, 178000, 176000])
    }
    console.log('PASS: structured 503/429 stop after three attempts within one request budget')

    const successful = { data: { audioContent: audio.toString('base64') } }
    const spaced = harness((_config, _call, _advance, sleep) => sleep(20000, successful))
    const distinct = Array.from({ length: 4 }, (_, i) => ({ ...input, text: `別の台詞 ${i}` }))
    const spacedAudio = await Promise.all([...distinct, distinct[0]].map(value => spaced.generate(value)))
    assert.equal(spaced.calls.length, 4)
    assert.deepEqual(spaced.startTimes, [0, 2000, 4000, 6000])
    assert.deepEqual(spaced.calls.map(call => call.timeout), [180000, 178000, 176000, 174000])
    assert.equal(spaced.now(), 26000)
    assert.ok(spacedAudio.every(buffer => buffer.equals(audio)))
    console.log('PASS: four different subtitles start two seconds apart while synthesis overlaps and identical work stays deduplicated')

    const sharedCooldown = harness(async (_config, call, _advance, sleep) => {
        if (call === 1) {
            await sleep(1000)
            throw googleError(429, 'RESOURCE_EXHAUSTED', 'Quota exceeded for the model.')
        }
        return successful
    })
    await Promise.all(distinct.map(value => sharedCooldown.generate(value)))
    assert.deepEqual(sharedCooldown.startTimes, [0, 31000, 33000, 35000, 37000])
    assert.equal(sharedCooldown.calls.filter(call => call.data === sharedCooldown.calls[0].data).length, 2)
    console.log('PASS: a 429 extends the cooldown for requests already queued, and the failed subtitle retries unchanged')

    for (const [retryDelay, headers, expected] of [
        ['45.5s', undefined, 45500],
        [{ seconds: '55', nanos: 500000000 }, undefined, 55500],
        ['45s', { 'retry-after': '60' }, 60000],
        [undefined, { get: name => name === 'retry-after' ? '50' : null }, 50000],
        [undefined, { 'Retry-After': 'Thu, 01 Jan 1970 00:00:50 GMT' }, 50000],
        ['600s', undefined, 120000],
        ['invalid', { 'retry-after': '-1' }, 30000],
    ]) {
        const advised = harness((_config, call) => {
            if (call > 1) return successful
            const error = googleError(429, 'RESOURCE_EXHAUSTED')
            if (retryDelay) error.response.data.error.details.push({ '@type': 'type.googleapis.com/google.rpc.RetryInfo', retryDelay })
            if (headers) error.response.headers = headers
            throw error
        })
        await advised.generate(input)
        assert.deepEqual(advised.startTimes, [0, expected])
        assert.equal(advised.calls[1].timeout, 180000 - expected)
    }
    console.log('PASS: Google retry durations and Retry-After seconds/dates are honored, invalid values ignored, and delays capped at 120 seconds')

    const waitingDeadline = harness((_config, _call, advance) => {
        advance(170000)
        throw googleError(429, 'RESOURCE_EXHAUSTED')
    })
    const expired = await Promise.allSettled(distinct.map(value => waitingDeadline.generate(value)))
    assert.equal(waitingDeadline.calls.length, 1)
    assert.ok(expired.every(result => result.status === 'rejected' && result.reason.noAudioProduced === true))
    assert.match(expired[1].reason.message, /대기 시간/)
    assert.ok(waitingDeadline.now() <= 180000)
    console.log('PASS: queued work that cannot fit the shared cooldown into its budget is rejected without sending or exceeding 180 seconds')

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
