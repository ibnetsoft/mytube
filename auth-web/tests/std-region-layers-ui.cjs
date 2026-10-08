const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('fs')
const path = require('path')
const ts = require('typescript')
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const source = fs.readFileSync(path.join(__dirname, '../components/StdRegionLayers.tsx'), 'utf8')
const localizedCopy = {}
new Function('exports', ts.transpileModule(fs.readFileSync(path.join(__dirname, '../lib/stdRegionMotionCopy.ts'), 'utf8'), { compilerOptions: {module:1,target:9} }).outputText)(localizedCopy)
const code = ts.transpileModule(source, { compilerOptions: { module: 1, target: 9, jsx: 4 } }).outputText

function render(pack, locale = "ko") {
    // A saved brush upload changes the geometry key and clears the package
    // one render before the previous preview URLs are cleaned up by the effect.
    const states = [pack, false, '', { background: 'blob:old', 'region:arm': 'blob:old' }, true, false, 12, 'erase', 1]
    const exports = {}
    new Function('exports', 'require', code)(exports, name => {
        if (name === 'react') return { ...React, useState: () => [states.shift(), () => {}], useEffect: () => {}, useRef: value => ({ current: value }) }
        if (name === '@/lib/stdRegionMotionCopy') return localizedCopy
        if (name === '@/lib/stdRegionMotion') return { regionLayerKey: () => 'current-key' }
        return require(name)
    })
    return renderToStaticMarkup(exports.default({ locale, projectId: 'test', headers: {}, number: 1, imageId: 'image', sha: 'sha', image: 'blob:source', regions: [{ id: 'arm', polygon: [], anchor: [.5, .5] }], selected: 0, backgroundAssetId: '', patch() {}, onBackground() {}, onReady() {}, onBusy() {}, locked: false }))
}

test('clearing a package while previous previews exist does not crash or show stale review controls', () => {
    const html = render(null)
    assert.match(html, /정밀 레이어 준비/)
    assert.doesNotMatch(html, /레이어 확정하고 재사용/)
})

test('changing geometry hides old approved previews before the fetch completes', () => {
    const html = render({ id: 'old', key: 'old-key', state: 'approved', result: { files: [{ role: 'region:arm' }] } })
    assert.doesNotMatch(html, /선택 부위 외곽선 브러시 수정/)
    assert.doesNotMatch(html, /레이어 확정하고 재사용/)
})

test('Thai mode translates layer controls and keeps Korean mode intact', () => {
 const html=render(null,'th'); assert.match(html,/เตรียมเลเยอร์อย่างละเอียด/); assert.match(html,/แยกเส้นขอบ/); assert.doesNotMatch(html,/[가-힣]/);
 assert.equal(localizedCopy.regionMotionText('설정 저장','th'),'บันทึกการตั้งค่า');
 assert.equal(localizedCopy.regionMotionText('설정 저장','ko'),'설정 저장');
})
