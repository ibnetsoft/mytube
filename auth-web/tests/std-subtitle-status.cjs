const assert = require('node:assert/strict')
const esbuild = require('esbuild')
const Module = require('node:module')
const path = require('node:path')
const entry = path.resolve(__dirname, '../lib/stdSubtitleStatus.ts')
const built = esbuild.buildSync({entryPoints: [entry], bundle: true, platform: 'node', format: 'cjs', write: false})
const mod = new Module(entry, module); mod.filename = entry; mod.paths = module.paths; mod._compile(built.outputFiles[0].text, entry)
const {localizeSubtitleStatus: localize} = mod.exports
const preview = '자막 미리듣기 준비 중... (32/716)'
assert.equal(localize(preview, 'ko'), preview)
for (const locale of ['en', 'vi', 'th']) {
  assert.match(localize(preview, locale), /32\/716/)
  assert.doesNotMatch(localize(preview, locale), /[가-힣]/)
  assert.doesNotMatch(localize('자막 미리듣기가 완료되었습니다.', locale), /[가-힣]/)
  assert.doesNotMatch(localize('씬 4의 자막 2개를 하나로 합쳤습니다.', locale), /[가-힣]/)
  assert.doesNotMatch(localize('알 수 없는 오류가 발생했습니다.', locale), /[가-힣]/)
}
assert.match(localize('씬 4의 자막 2개를 하나로 합쳤습니다.', 'en'), /2.*4/)
console.log('Subtitle status translations passed')
