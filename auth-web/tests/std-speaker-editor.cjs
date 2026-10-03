const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const ts = require('typescript');

const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value)
    ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)];
const text = value => value == null || typeof value === 'boolean' ? '' : Array.isArray(value)
    ? value.map(text).join(' ') : typeof value === 'object' ? text(value.props?.children) : String(value);
const radios = tree => tree.filter(node => node.type === 'input' && node.props.type === 'radio');
const radio = (tree, value) => radios(tree).find(node => node.props.value === value);
const button = (tree, label) => tree.find(node => node.type === 'button' && text(node) === label);
let networkCalls = 0;
global.fetch = async () => { networkCalls++; throw new Error('Unexpected network request in speaker editor test'); };
global.document = { body: {} };

function harness(overrides = {}) {
    const state = [], refs = [];
    let index = 0, refIndex = 0, closed = 0;
    const saved = [];
    const react = {
        useState(initial) {
            const current = index++;
            if (!(current in state)) state[current] = typeof initial === 'function' ? initial() : initial;
            return [state[current], next => { state[current] = typeof next === 'function' ? next(state[current]) : next; }];
        },
        useMemo: callback => callback(),
        useCallback: callback => callback,
        useEffect() {},
        useRef(initial) { return refs[refIndex++] ??= { current: initial }; },
        useId: () => 'speaker-editor-test',
    };
    const cache = new Map();
    function load(filename) {
        const full = path.resolve(filename);
        if (cache.has(full)) return cache.get(full);
        const exports = {};
        cache.set(full, exports);
        new Function('exports', 'require', ts.transpile(fs.readFileSync(full, 'utf8'), { module: 1, target: 7, jsx: 4 }))(exports, id => {
            if (id === 'react') return react;
            if (id === 'react-dom') return { createPortal: child => child };
            if (id === 'react/jsx-runtime') return jsx;
            const base = id.startsWith('@/') ? path.resolve('auth-web', id.slice(2)) : path.resolve(path.dirname(full), id);
            for (const ext of ['.ts', '.tsx', '.js']) if (fs.existsSync(base + ext)) return load(base + ext);
            return require(id);
        });
        return exports;
    }
    const component = load('auth-web/components/SubtitleSpeakerEditor.tsx').default;
    const props = {
        speaker: { name: '仙太郎', gender: 'male', label: '仙太郎' },
        names: ['仙太郎', '花代', '見知らぬ人'],
        characters: [{ name: '仙太郎', gender: 'male' }, { name: '花代', gender: 'female' }],
        locale: 'ko',
        translations: { ko: { '仙太郎': '센타로', '花代': '하나요', '見知らぬ人': '낯선 사람' }, th: { '仙太郎': 'เซ็นทาโร', '花代': 'ฮานาโย', '見知らぬ人': 'คนแปลกหน้า' } },
        onSave: async (...values) => saved.push(values),
        onClose: () => closed++,
        ...overrides,
    };
    return {
        props, saved, assignment: load('auth-web/lib/stdSpeakerAssignment.ts'),
        get closed() { return closed; },
        render() { index = refIndex = 0; return nodes(component(props)); },
    };
}

(async () => {
    for (const [locale, title, save, cancel, localizedName] of [
        ['ko', '화자 확인', '저장', '취소', '센타로'],
        ['th', 'ยืนยันผู้พูด', 'บันทึก', 'ยกเลิก', 'เซ็นทาโร'],
    ]) {
        const h = harness({ locale });
        let tree = h.render();
        const dialog = tree.find(node => node.props?.role === 'dialog');
        assert(dialog, `${locale}: accessible dialog`);
        assert.equal(dialog.props['aria-label'], title);
        assert(!tree.some(node => node.type === 'select' || node.type === 'datalist'), 'Both choices use visible radio buttons');
        assert(text(dialog).includes(`仙太郎 (${localizedName})`), `${locale}: original name followed by localized name`);
        assert(!new RegExp(locale === 'th' ? '[가-힣]' : '[ก-๙]').test(text(dialog)), `${locale}: no UI text leaks from the other locale`);
        assert.equal(radio(tree, '仙太郎').props.checked, true);
        assert.equal(radio(tree, 'male').props.checked, true);
        assert.notEqual(radio(tree, '仙太郎').props.name, radio(tree, 'male').props.name);
        assert(button(tree, save)); assert(button(tree, cancel));
        await button(tree, save).props.onClick();
        assert.deepEqual(h.saved, [['仙太郎', 'male']], 'Save canonical original name, never the display translation');
        assert.equal(h.closed, 1);
    }

    const h = harness();
    let tree = h.render();
    radio(tree, '花代').props.onChange({ target: { value: '花代', checked: true } });
    tree = h.render();
    assert.equal(radio(tree, 'female').props.checked, true, 'Selecting a known character loads its gender');
    radio(tree, '見知らぬ人').props.onChange({ target: { value: '見知らぬ人', checked: true } });
    tree = h.render();
    assert.equal(radio(tree, '').props.checked, true, 'An unknown character never inherits the previous gender');
    radio(tree, 'male').props.onChange({ target: { value: 'male', checked: true } });
    tree = h.render();
    await button(tree, '저장').props.onClick();
    assert.deepEqual(h.saved, [['見知らぬ人', 'male']]);

    const custom = harness();
    tree = custom.render();
    radio(tree, '__custom__').props.onChange({ target: { checked: true } });
    tree = custom.render();
    assert.equal(radio(tree, '').props.checked, true, 'Custom names start with unconfirmed gender');
    assert.equal(button(tree, '저장').props.disabled, true, 'A blank custom name cannot be saved');
    const nameInput = tree.find(node => node.type === 'input' && node.props.type !== 'radio');
    assert(nameInput, 'The custom radio exposes an editable name input');
    nameInput.props.onChange({ target: { value: '  お婆さん  ' } });
    tree = custom.render();
    radio(tree, 'female').props.onChange({ target: { value: 'female', checked: true } });
    tree = custom.render();
    await button(tree, '저장').props.onClick();
    assert.deepEqual(custom.saved, [['お婆さん', 'female']], 'Custom names are trimmed but not translated before saving');

    const unassigned = harness({ speaker: null });
    tree = unassigned.render();
    assert.equal(button(tree, '저장').props.disabled, true);
    assert.equal(radios(tree).filter(node => node.props.name === 'subtitle-speaker-name' && node.props.checked).length, 0);

    const { speakerNameLabel, subtitleSpeaker } = h.assignment;
    const localizedCast = [{ name: '仙太郎', name_ko: '센타로', name_th: 'เซ็นทาโร', gender: 'male' }];
    assert.equal(speakerNameLabel('仙太郎', localizedCast, 'ko'), '仙太郎 (센타로)');
    assert.equal(speakerNameLabel('仙太郎', localizedCast, 'th'), '仙太郎 (เซ็นทาโร)');
    assert.equal(speakerNameLabel('仙太郎', [], 'ko'), '仙太郎', 'Missing translations leave the original visible');
    assert.equal(speakerNameLabel('덕수', [{ name: '덕수', name_ko: '덕수' }], 'ko'), '덕수', 'Identical local/original names are not repeated');
    const annotated = { text: '本文', editor_speaker: { name: '仙太郎', gender: 'male', text: '本文' } };
    assert.deepEqual(subtitleSpeaker(annotated, undefined, localizedCast, 'th'), { name: '仙太郎', gender: 'male', label: '仙太郎 (เซ็นทาโร)' });

    const failure = harness({ onSave: async () => { throw new Error('save failed'); } });
    tree = failure.render();
    await button(tree, '저장').props.onClick();
    tree = failure.render();
    assert(tree.some(node => node.props?.role === 'alert'), 'Failed saves show an error');
    assert.equal(failure.closed, 0, 'Failed saves keep the editor open');
    assert.equal(button(tree, '저장').props.disabled, false, 'A failed save can be retried');
    button(tree, '취소').props.onClick();
    assert.equal(failure.closed, 1);

    const thaiFailure = harness({ locale: 'th', onSave: async () => { throw new Error('save failed'); } });
    tree = thaiFailure.render();
    await button(tree, 'บันทึก').props.onClick();
    tree = thaiFailure.render();
    assert.equal(text(tree.find(node => node.props?.role === 'alert')), 'บันทึกไม่สำเร็จ');
    assert.equal(thaiFailure.closed, 0);

    let finishSaving;
    const pending = harness({ locale: 'th', onSave: () => new Promise(resolve => { finishSaving = resolve; }) });
    tree = pending.render();
    const saving = button(tree, 'บันทึก').props.onClick();
    tree = pending.render();
    assert.equal(button(tree, 'กำลังบันทึก…').props.disabled, true);
    assert.equal(button(tree, 'ยกเลิก').props.disabled, true);
    assert(tree.filter(node => node.type === 'fieldset').every(node => node.props.disabled));
    finishSaving();
    await saving;
    assert.equal(pending.closed, 1);

    assert.equal(networkCalls, 0);
    console.log('PASS: Korean/Thai speaker editor labels, original/localized names, native radio choices, canonical/custom save values, character gender transitions, save locking and failed-save recovery');
})().catch(error => { console.error(error); process.exitCode = 1; });
