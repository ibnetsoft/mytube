const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const vm = require('node:vm')

const source = fs.readFileSync(require.resolve('../lib/stdSubtitleTranslation.ts'), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
const moduleBox = { exports: {} }
vm.runInNewContext(js, { module: moduleBox, exports: moduleBox.exports, require })

const { buildSubtitleTranslationPrompt, isSubtitleTranslationLanguage, parseStrictTranslationResponse, translationMapFromBlocks } = moduleBox.exports
const sourceBlocks = [{ id: 'b0', text: '그가 말했다. "가지 마."' }, { id: 'b1', text: '비가 내렸다.' }]
for (const [language, name] of [['ko', 'Korean'], ['en', 'English'], ['vi', 'Vietnamese'], ['th', 'Thai']]) {
    assert.equal(isSubtitleTranslationLanguage(language), true)
    const prompt = buildSubtitleTranslationPrompt(sourceBlocks, language)
    assert.match(prompt, new RegExp(name))
    assert.match(prompt, /Never merge, split, summarize/)
    assert.match(prompt, /Preserve direct speech as direct speech/)
}
assert.equal(isSubtitleTranslationLanguage('xx'), false)

const parsed = parseStrictTranslationResponse(JSON.stringify({ translations: [
    { id: 'b0', translation: 'เขาพูดว่า “อย่าไป”' },
    { id: 'b1', translation: 'ฝนตก' },
] }), sourceBlocks)
assert.equal(parsed.length, 2)
assert.throws(() => parseStrictTranslationResponse('{"translations":[{"id":"b0","translation":"x"}]}', sourceBlocks), /every subtitle block/)

const map = translationMapFromBlocks([{ index: 0, source_text: sourceBlocks[0].text, translated_text: parsed[0].translation }])
assert.equal(Object.values(map)[0], parsed[0].translation)
console.log('std subtitle translation tests passed')

const { remapSubtitleTranslations, remapSubtitleTranslationMap, subtitleTranslationKey } = moduleBox.exports
const oldTexts = ['반복', '내가 잘못했다.', '겁이 나서 그랬어.', '반복', ...Array.from({ length: 312 }, (_, i) => `정상 문장 ${i}`)]
const saved = oldTexts.map((source_text, index) => ({ index, source_text, translated_text: `태국어 원본 ${index}` }))
const merged = [oldTexts[0], oldTexts[1] + ' ' + oldTexts[2], ...oldTexts.slice(3)]
const aligned = remapSubtitleTranslations(saved, merged.map((source_text, index) => ({ index, source_text })))
assert.equal(aligned.length, merged.length - 1)
assert.equal(aligned[1].translated_text, '태국어 원본 3', 'Repeated sentences must consume separate original translations')
const display = remapSubtitleTranslationMap(translationMapFromBlocks(saved), merged.map(text => ({ text })))
assert.equal(display[subtitleTranslationKey(1, merged[1])], undefined, 'Only the merged block waits for translation')
for (let index = 2; index < merged.length; index++) {
    assert.equal(display[subtitleTranslationKey(index, merged[index])], saved[index + 1].translated_text)
}
const split = ['반복', '내가', '잘못했다.', ...oldTexts.slice(2)]
const splitMap = translationMapFromBlocks(remapSubtitleTranslations(saved, split.map((source_text, index) => ({ index, source_text }))))
assert.equal(splitMap[subtitleTranslationKey(4, '반복')], saved[3].translated_text)
assert.equal(Object.keys(remapSubtitleTranslationMap({}, merged.map(text => ({ text })))).length, 0)
console.log('subtitle merge/split preserves every unchanged translation before any API response')

// Execute the route's cache selection so the regression also covers API input.
const route = fs.readFileSync(require.resolve('../app/api/std/projects/[projectId]/subtitle-translations/route.ts'), 'utf8')
const selection = route.slice(route.indexOf('    const cachedBlocks ='), route.indexOf('    if (body.job_id)', route.indexOf('    const cachedBlocks =')))
const selectMissing = new Function('targets', 'project', 'targetLanguage', 'blocks', 'translationMapFromBlocks', 'remapSubtitleTranslations', 'subtitleTranslationKey',
    ts.transpile(selection + '\nreturn missing', { target: ts.ScriptTarget.ES2020 }))
const missing = selectMissing(null, { project_payload: { subtitle_translations: { th: { blocks: saved } } } }, 'th',
    merged.map((source_text, index) => ({ index, source_text })), translationMapFromBlocks, remapSubtitleTranslations, subtitleTranslationKey)
assert.deepEqual(missing, [{ index: 1, source_text: merged[1] }])
console.log('API translates only the merged sentence in a 316-block project')

assert.doesNotMatch(route, /generateJsonWithModelSetting|geminiApiKey|OPENAI_API_KEY|GEMINI_API_KEY/)
const { subtitleTranslationIndexes } = moduleBox.exports
const manualRows = [{ text: 'normal' }, { text: 'merged one', translation_manual: true }, { text: 'merged two', translation_manual: true }]
assert.deepEqual(Array.from(subtitleTranslationIndexes(manualRows)), [0])
assert.deepEqual(Array.from(subtitleTranslationIndexes(JSON.parse(JSON.stringify(manualRows)), 2)), [2])
const targetedMissing = selectMissing(new Set([2]), { project_payload: {} }, 'th',
    manualRows.map((s, index) => ({ index, source_text: s.text })), translationMapFromBlocks, remapSubtitleTranslations, subtitleTranslationKey)
assert.deepEqual(targetedMissing.map(b => b.index), [2])
console.log('manual merged blocks stay out of automatic requests; clicking targets only one row')

async function verifyLocalQueueRoute() {
    const tables = {
        std_projects: [{ id: 'project-test', employee_email: 'tester@example.test', project_payload: {} }],
        global_settings: [{ key: 'sys_api_subtitle_translation_scope', value: 'all' }],
        std_subtitle_translation_jobs: [],
    }
    const database = { from(table) {
        const filters = []
        return {
            select() { return this },
            eq(key, value) { filters.push([key, value]); return this },
            async maybeSingle() { return { data: tables[table].find(row => filters.every(([k, v]) => row[k] === v)) || null } },
            async single() { return this.maybeSingle() },
            async upsert(row) { tables[table].push({ ...row, id: 'job-test', status: 'queued' }); return { error: null } },
        }
    } }
    const compiled = ts.transpileModule(route, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS } }).outputText
    const routeModule = { exports: {} }
    const localRequire = name => {
        if (name === 'next/server') return { NextResponse: { json: (data, options = {}) => ({ data, status: options.status || 200 }) } }
        if (name === '@/lib/stdWeb') return { requireStdUser: async () => ({ ok: true, requester: { email: 'tester@example.test' } }) }
        if (name === '@/lib/supabaseAdmin') return { supabaseAdmin: database }
        if (name === '@/lib/stdSubtitleTranslation') return moduleBox.exports
        return require(name)
    }
    vm.runInNewContext(compiled, { exports: routeModule.exports, require: localRequire, console, URL, Set, Map })
    const input = { target_language: 'ko', blocks: [{ index: 0, source_text: 'お鈴は笑った。' }] }
    const request = data => new Request('http://localhost/api/std/projects/project-test/subtitle-translations', {
        method: 'POST', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' },
    })
    const queued = await routeModule.exports.POST(request(input), { params: { projectId: 'project-test' } })
    assert.equal(queued.status, 202)
    assert.equal(queued.data.provider, 'local-codex')
    assert.equal(tables.std_subtitle_translation_jobs.length, 1)
    const pending = await routeModule.exports.POST(request({ ...input, job_id: 'job-test' }), { params: { projectId: 'project-test' } })
    assert.equal(pending.status, 202)
    tables.std_subtitle_translation_jobs[0].status = 'completed'
    tables.std_subtitle_translation_jobs[0].result_blocks = [{ ...input.blocks[0], translated_text: '오스즈는 웃었다.' }]
    const done = await routeModule.exports.POST(request({ ...input, job_id: 'job-test' }), { params: { projectId: 'project-test' } })
    assert.equal(done.status, 200)
    assert.equal(done.data.blocks[0].translated_text, '오스즈는 웃었다.')
    const changed = await routeModule.exports.POST(request({ ...input, job_id: 'job-test', blocks: [{ index: 0, source_text: 'changed' }] }), { params: { projectId: 'project-test' } })
    assert.equal(changed.status, 409, 'An old job cannot supply a translation for edited source text')
    console.log('Web route queues local jobs, polls completion, and rejects stale source without any model API')
}
verifyLocalQueueRoute().catch(error => { console.error(error); process.exitCode = 1 })
