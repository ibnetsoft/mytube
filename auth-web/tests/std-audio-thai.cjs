const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const ts = require('../node_modules/typescript');
const cache = {};
function load(file, overrides = {}) {
    const full = path.resolve(file);
    if (!Object.keys(overrides).length && cache[full]) return cache[full];
    const exports = {};
    const code = ts.transpileModule(fs.readFileSync(full, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;
    new Function('exports', 'require', code)(exports, id => overrides[id] || load(
        id.startsWith('@/') ? `auth-web/${id.slice(2)}.ts` : path.resolve(path.dirname(full), `${id}.ts`)
    ));
    if (!Object.keys(overrides).length) cache[full] = exports;
    return exports;
}
const { sfxDescription, sfxDescriptionKo } = load('auth-web/lib/stdSfxDescriptions.ts');
const { sfxDescriptionsTh } = load('auth-web/lib/stdSfxDescriptionsTh.ts');
const { stdUiText } = load('auth-web/lib/stdUiText.ts');
const asset = { id: 'pop', file_name: 'bubble-pop.mp3', metadata: { description_ko: '물방울이 팝 터지는 소리' } };
assert.equal(sfxDescription(asset, 'ko'), sfxDescriptionKo(asset));
assert.equal(sfxDescription(asset, 'th'), 'เสียงฟองอากาศแตกดังป๊อป');
assert.equal(sfxDescription({ metadata: { description_th: 'เสียงเฉพาะ' } }, 'th'), 'เสียงเฉพาะ');
assert.ok(!/[가-힣]/.test(sfxDescription({ metadata: { description_ko: '새로운 설명' } }, 'th')));
assert.equal(stdUiText('th', '{n}번 씬', { n: 100 }), 'ฉากที่ 100');
for (const [description, translated] of Object.entries(sfxDescriptionsTh)) {
    assert.ok(/[ก-๙]/.test(translated) && !/[가-힣]/.test(translated), description);
}
// Render the real picker, including its portal, in both roles and test Thai search.
global.document = { body: {} };
function strings(node) {
    if (typeof node === 'string') return node;
    if (Array.isArray(node)) return node.map(strings).join(' ');
    if (!node?.props) return '';
    return [node.props['aria-label'], node.props.placeholder, strings(node.props.children)].filter(Boolean).join(' ');
}
function render(role, search = '', assets = [asset]) {
    let index = 0;
    const jsx = (type, props) => ({ type, props });
    const Picker = load('auth-web/components/SubtitleSfxPicker.tsx', {
        react: { useState: initial => { const n = index++; return [n === 2 ? true : n === 3 ? search : initial, () => {}]; }, useEffect() {}, useRef: () => ({ current: null }) },
        'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' },
        'react-dom': { createPortal: node => node },
    }).default;
    return strings(Picker({ locale: 'th', role, assets, value: '', projectId: 'p', headers: {}, onChange() {}, onOpen() {}, onUpload() {} }));
}
for (const role of ['sfx', 'bgm']) {
    assert.ok(!/[가-힣]/.test(render(role)), `${role} picker leaked Korean`);
    assert.ok(!/[가-힣]/.test(render(role, '', [])), `${role} empty picker leaked Korean`);
}
assert.ok(render('sfx', 'ฟองอากาศ').includes('bubble-pop.mp3'));
assert.ok(!render('sfx', 'ไม่ตรงกับเสียง').includes('bubble-pop.mp3'));
assert.ok(render('sfx', 'BUBBLE').includes('bubble-pop.mp3'));
if (process.env.SFX_CATALOG_FIXTURE) {
    const assets = JSON.parse(fs.readFileSync(process.env.SFX_CATALOG_FIXTURE, 'utf8'));
    for (const item of assets) {
        assert.ok(sfxDescriptionsTh[sfxDescriptionKo(item)], `Missing catalog translation: ${item.file_name}`);
        assert.ok(!/[가-힣]/.test(sfxDescription(item, 'th')));
    }
    console.log(`PASS: all ${assets.length} shared catalog descriptions translated`);
}
console.log('PASS: Thai SFX/BGM picker labels, empty states, description search, fallback and original Korean');
