const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const ts = require('typescript')
function load(relative, mocks = {}, suffix = '') {
    const filename = path.resolve(__dirname, '..', relative)
    const mod = new Module(filename, module)
    mod.filename = filename
    mod.paths = Module._nodeModulePaths(path.dirname(filename))
    const original = mod.require.bind(mod)
    mod.require = id => Object.hasOwn(mocks, id) ? mocks[id] : id.startsWith('@/') ? {} : original(id)
    mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8') + suffix, {
        compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true},
    }).outputText, filename)
    return mod.exports
}
async function main() {
    const names=['VERCEL','GCP_PROJECT_NUMBER','GCP_WORKLOAD_IDENTITY_POOL_ID','GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID','GCP_SERVICE_ACCOUNT_EMAIL']
    const saved=Object.fromEntries(names.map(name=>[name,process.env[name]]))
    try {
        names.forEach(name=>delete process.env[name])
        let config, adcCalls=0, tokenCalls=0
        const auth=load('lib/voiceStudioAuth.ts', {
            'google-auth-library': {
                GoogleAuth:class {getClient(){adcCalls++;return Promise.resolve('adc')}},
                ExternalAccountClient:{fromJSON(value){config=value;return {kind:'federated'}}},
            },
            '@vercel/oidc':{getVercelOidcToken(){tokenCalls++;return 'test-token'}},
        })
        assert.equal(await auth.voiceStudioAuth('test-project'),'adc')
        process.env.VERCEL='1'
        await assert.rejects(auth.voiceStudioAuth('test-project'),/설정이 누락/)
        assert.equal(adcCalls,1)
        process.env.GCP_PROJECT_NUMBER='123'
        process.env.GCP_WORKLOAD_IDENTITY_POOL_ID='pool'
        process.env.GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID='provider'
        process.env.GCP_SERVICE_ACCOUNT_EMAIL='voice@test.iam.gserviceaccount.com'
        assert.equal((await auth.voiceStudioAuth('test-project')).kind,'federated')
        assert.equal(config.audience,'//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/pool/providers/provider')
        assert.equal(config.service_account_impersonation_url,'https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/voice@test.iam.gserviceaccount.com:generateAccessToken')
        assert.equal(tokenCalls,0)
        assert.equal(await config.subject_token_supplier.getSubjectToken(),'test-token')
        assert.equal(tokenCalls,1)
    } finally {
        names.forEach(name=>saved[name]===undefined?delete process.env[name]:process.env[name]=saved[name])
    }
    console.log('PASS: local ADC; production fails closed; OIDC federation configuration and token supplier')
    const catalog = load('lib/voiceStudioCatalog.ts')
    assert.equal(catalog.VOICE_STUDIO_VOICES.length, 30)
    assert.throws(() => catalog.voiceStudioName('gemini:invalid'))
    const merged=catalog.mergeVoiceStudioSegments([{voiceId:'gemini:Charon',text:'첫 줄'},{voiceId:'gemini:Charon',text:'둘째 줄'},{voiceId:'actor-id',text:'대사'},{voiceId:'gemini:Charon',text:'마지막'}])
    assert.equal(merged.length,3)
    assert.equal(merged[0].text,'첫 줄\n둘째 줄')
    const calls = []
    const route = load('app/api/std/projects/[projectId]/tts/generate/route.ts', {
        '@/lib/voiceStudioCatalog': catalog,
        '@/lib/stdVoiceStudio': {generateVoiceStudioMp3: async input => {calls.push(['gemini', input]);return Buffer.alloc(300, 1)}},
    }, '\nexport { generateElevenLabsMp3 };')
    global.fetch = async (url, options) => {
        assert.ok(url.includes('/actor-id?'))
        calls.push(['elevenlabs', JSON.parse(options.body)])
        return {ok:true, headers:new Headers({'content-type':'audio/mpeg'}), arrayBuffer:async()=>new Uint8Array(300).fill(2).buffer}
    }
    const result = await route.generateElevenLabsMp3({apiKeys:['test'],voiceId:'actor-id',modelId:'eleven_multilingual_v2',text:'unused',
        voiceSegments:[{text:'나레이션',voiceId:'gemini:Charon',direction:'담담하게'},{text:'대사',voiceId:'actor-id'},{text:'끝',voiceId:'gemini:Kore'}]})
    assert.deepEqual(calls.map(c=>c[0]), ['gemini','elevenlabs','gemini'])
    assert.equal(calls[0][1].direction,'담담하게')
    assert.equal(result.audioBuffer.length,900)
    assert.deepEqual([result.audioBuffer[0],result.audioBuffer[300],result.audioBuffer[600]],[1,2,1])
    const failRoute=load('app/api/std/projects/[projectId]/tts/generate/route.ts', {
        '@/lib/voiceStudioCatalog':catalog,
        '@/lib/stdVoiceStudio':{generateVoiceStudioMp3:async()=>{throw new Error('Cloud unavailable')}},
    }, '\nexport { generateElevenLabsMp3 };')
    const before=calls.length
    await assert.rejects(failRoute.generateElevenLabsMp3({apiKeys:['test'],voiceId:'actor-id',text:'narration',modelId:'eleven_multilingual_v2',voiceSegments:[{text:'나레이션',voiceId:'gemini:Charon'}]}),/Cloud unavailable/)
    assert.equal(calls.length,before)
    console.log('PASS: 30 voices; mixed provider ordering; direction propagation; no ElevenLabs fallback on Gemini failure')
}
main().catch(error=>{console.error(error);process.exitCode=1})
