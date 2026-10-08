const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const ts = require('typescript')

const root = path.resolve(__dirname, '..')
const moduleExports = {}
new Function('exports', ts.transpile(fs.readFileSync(path.join(root, 'lib/voiceDescriptionLocale.ts'), 'utf8'), {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
}))(moduleExports)
const { localizedVoiceDescription } = moduleExports
const catalog = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/voice-description-catalog.json'), 'utf8'))
const locales = ['ko', 'en', 'vi', 'th']
const fallback = Object.fromEntries(locales.map(locale => [locale, localizedVoiceDescription({ description: '未知の説明' }, locale)]))
const originalCatalog = JSON.stringify(catalog)
assert.equal(catalog.length, 48)
assert.equal(new Set(catalog.map(v => v.description).filter(Boolean)).size, 44)

for (const voice of catalog) {
    for (const locale of locales) {
        const result = localizedVoiceDescription(voice, locale)
        if (!voice.description) {
            assert.equal(result, '', `${voice.name}: empty description is left to the provider fallback`)
            continue
        }
        assert(result && result !== fallback[locale], `${voice.name}: missing ${locale} translation`)
        if (locale === 'th') {
            assert(/[\u0e00-\u0e7f]/.test(result), `${voice.name}: Thai description required`)
            assert(!/[가-힣\u3040-\u30ff\u3400-\u9fff]/.test(result), `${voice.name}: foreign copy in Thai description`)
            const preservedNames = new Set(['Saori', 'Everett', 'Alex', 'Vox', 'Julian', 'YohanKoo', 'Flint', 'Mio'])
            for (const word of result.match(/[A-Za-z]+/g) || []) {
                assert(preservedNames.has(word), `${voice.name}: untranslated Thai word ${word}`)
            }
        }
        if (locale === 'en' && !/[가-힣]/.test(voice.description)) assert.equal(result, voice.description)
    }
}
assert.equal(JSON.stringify(catalog), originalCatalog, 'localizing descriptions must not change voice names or original metadata')

// The API and the page have separate fallback catalogs. Check both independently
// so adding a fallback voice cannot silently leave its description untranslated.
for (const filename of ['app/api/std/voices/route.ts', 'app/std/page.tsx']) {
    const source = ts.createSourceFile(filename, fs.readFileSync(path.join(root, filename), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    let count = 0
    const visit = node => {
        if (ts.isPropertyAssignment(node) && node.name.getText(source) === 'description'
            && ts.isStringLiteral(node.initializer)) {
            const description = node.initializer.text
            // Page descriptions after the catalog are modal help text, localized separately.
            if (filename.endsWith('page.tsx') && source.getLineAndCharacterOfPosition(node.pos).line > 800) return
            count++
            for (const locale of locales) assert.notEqual(localizedVoiceDescription({ description }, locale), fallback[locale], `${filename}: ${locale}: ${description}`)
        }
        ts.forEachChild(node, visit)
    }
    visit(source)
    assert.equal(count, 22, `${filename}: all preset and free voice descriptions checked`)
}

const sample = catalog.find(v => v.name.startsWith('Yukari'))
const whitespaceVariant = { description: `  ${sample.description.replace(/ /g, '\n  ')}  ` }
assert.equal(localizedVoiceDescription(whitespaceVariant, 'th'), localizedVoiceDescription(sample, 'th'))
assert.equal(localizedVoiceDescription({ description: 'A brand new voice for narration.' }, 'en'), 'A brand new voice for narration.')
assert.equal(localizedVoiceDescription({ description: '새롭게 추가한 차분한 목소리입니다.' }, 'ko'), '새롭게 추가한 차분한 목소리입니다.')
assert.equal(localizedVoiceDescription({ description: '새로운 English 목소리' }, 'ko'), fallback.ko)
assert.equal(localizedVoiceDescription({ description: 'A voice พร้อมเสียงไทย' }, 'en'), fallback.en)
assert.equal(localizedVoiceDescription({ description: 'An unknown future voice.' }, 'th'), fallback.th)
assert.equal(localizedVoiceDescription({ description: 'An unknown future voice.' }, 'vi'), fallback.vi)
assert.equal(localizedVoiceDescription({ description: 'An unknown future voice.', description_i18n: { th: '  เสียงใหม่ที่แปลแล้ว  ' } }, 'th'), 'เสียงใหม่ที่แปลแล้ว')
assert.equal(localizedVoiceDescription({ description: 'Warm resonance that instantly captivates listeners.', description_i18n: { ko: '직접 작성한 설명' } }, 'ko'), '직접 작성한 설명')
assert.equal(localizedVoiceDescription({ description: '   ' }, 'th'), '')
console.log('PASS: 48 current voices, 44 descriptions, API/page fallback catalogs, all four locales, preserved names and metadata, whitespace normalization, supplied translations and safe unknown-description fallback')
