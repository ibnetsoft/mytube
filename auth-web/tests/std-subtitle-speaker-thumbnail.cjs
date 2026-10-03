const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')
const ts = require('typescript')

const nodes = value => !value || typeof value !== 'object' ? [] : Array.isArray(value)
    ? value.flatMap(nodes) : [value, ...nodes(value.props?.children)]
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) }
const thumbnail = '/api/std/projects/project-a/character-thumbnail?slot=2'
const speaker = { name: '仙太郎', gender: 'male', label: '仙太郎 (센타로)' }
const character = { name: '仙太郎', name_ko: '센타로', image_url: thumbnail }

function harness(overrides = {}) {
    const state = [], saved = []
    let index = 0
    const react = {
        Fragment: 'fragment', useEffect() {},
        useState(initial) {
            const slot = index++
            if (!(slot in state)) state[slot] = typeof initial === 'function' ? initial() : initial
            return [state[slot], next => { state[slot] = typeof next === 'function' ? next(state[slot]) : next }]
        },
    }
    const cache = new Map()
    function load(filename) {
        const full = path.resolve(filename)
        if (cache.has(full)) return cache.get(full)
        const exports = {}
        cache.set(full, exports)
        new Function('exports', 'require', ts.transpile(fs.readFileSync(full, 'utf8'), { module: 1, target: 7, jsx: 4 }))(exports, id => {
            if (id === 'react') return react
            if (id === 'react/jsx-runtime') return jsx
            if (id === '@/components/SubtitleSfxPicker') return { default: 'sfx-picker' }
            const base = id.startsWith('@/') ? path.resolve(__dirname, '..', id.slice(2)) : path.resolve(path.dirname(full), id)
            return load(`${base}.ts`)
        })
        return exports
    }
    const Editor = load(path.resolve(__dirname, '../components/SubtitleSfxEditor.tsx')).default
    const subtitle = { id: 'caption-a', text: '문을 열고 들어왔다', scene_number: 5, start_num: 10, end_num: 16 }
    const props = {
        locale: 'ko', speaker, characters: [character], projectId: 'project-a', headers: {},
        subtitle, subtitleIndex: 0, subtitles: [subtitle], assets: [{ id: 'sound', file_name: 'door.mp3' }],
        cues: [], selectedAssetId: 'sound', activeTokenIndex: 1,
        onSelect() {}, onEdit() {}, onPreviewOpen() {},
        onError(message) { throw new Error(message) }, onSave: async cues => { saved.push(cues) }, ...overrides,
    }
    return { props, saved, render() { index = 0; return nodes(Editor(props)) } }
}

test('the selected speaker gets the saved character portrait before subtitle words regardless of gender', () => {
    for (const gender of ['male', 'female', '']) {
        const h = harness({ speaker: { ...speaker, gender }, characters: [{ ...character, name: ' 仙太郎 ' }] })
        const tree = h.render()
        const images = tree.filter(node => node.type === 'img')
        assert.equal(images.length, 1)
        assert.equal(images[0].props.src, thumbnail)
        assert.match(images[0].props.alt, /仙太郎 \(센타로\)/)
        assert.equal(images[0].props.width, 32)
        assert.equal(images[0].props.height, 32)
        const firstWord = tree.findIndex(node => node.type === 'button' && node.props.children === '문을')
        assert(tree.indexOf(images[0]) < firstWord)
    }
})

test('narration, unknown speakers and missing images do not show a misleading character', () => {
    for (const props of [
        { speaker: null }, { speaker: undefined }, { speaker: { ...speaker, name: '見知らぬ人' } },
        { speaker: { ...speaker, name: '센타로' } }, { speaker: { ...speaker, name: '仙太郎 (센타로)' } },
        { characters: [] }, { characters: [{ ...character, image_url: '' }] },
        { characters: [{ ...character, image_url: 'blob:expired-session' }] },
    ]) {
        assert.equal(harness(props).render().filter(node => node.type === 'img').length, 0)
    }
    const thai = harness({ locale: 'th', speaker: { ...speaker, label: '仙太郎 (เซ็นทาโร)' } }).render()
    assert.match(thai.find(node => node.type === 'img').props.alt, /仙太郎 \(เซ็นทาโร\)/)
})

test('a failed portrait disappears but does not hide the next speaker portrait', () => {
    const h = harness()
    h.render().find(node => node.type === 'img').props.onError({ currentTarget: { style: {} } })
    assert.equal(h.render().filter(node => node.type === 'img').length, 0)
    h.props.speaker = { name: 'お鈴', gender: 'female', label: 'お鈴 (오스즈)' }
    h.props.characters = [{ name: 'お鈴', image_url: '/api/std/projects/project-a/character-thumbnail?slot=0' }]
    const image = h.render().find(node => node.type === 'img')
    assert(image)
    assert.equal(image.props.src, '/api/std/projects/project-a/character-thumbnail?slot=0')
})

test('only protected same-origin portrait URLs receive the impersonated user query', () => {
    const email = 'editor+thai@example.com'
    const headers = { 'x-impersonate-email': email, Authorization: 'Bearer must-not-enter-the-url' }
    const protectedImage = harness({ headers }).render().find(node => node.type === 'img')
    const url = new URL(protectedImage.props.src, 'https://studio.airing.work')
    assert.equal(url.searchParams.get('slot'), '2')
    assert.equal(url.searchParams.get('impersonate'), email)
    assert(!protectedImage.props.src.includes('must-not-enter-the-url'))
    for (const image_url of [
        'https://images.example.com/character.png',
        'https://images.example.com/api/std/projects/project-a/character-thumbnail?slot=2',
        '/other-image.png',
    ]) {
        const image = harness({ headers, characters: [{ ...character, image_url }] }).render().find(node => node.type === 'img')
        assert.equal(image.props.src, image_url)
    }
})

test('the portrait does not create a speech token or alter sound-effect boundary timing', async () => {
    const h = harness()
    const original = structuredClone(h.props.subtitle)
    const tree = h.render()
    const words = tree.filter(node => node.type === 'button' && ['문을', '열고', '들어왔다'].includes(node.props.children))
    assert.deepEqual(words.map(node => node.props.children), ['문을', '열고', '들어왔다'])
    assert.match(words[1].props.className, /border-cyan-400/)
    const boundaries = tree.filter(node => node.type === 'button' && /번째 단어 뒤 효과음 삽입$/.test(node.props['aria-label'] || ''))
    assert.equal(boundaries.length, 4)
    boundaries[1].props.onClick()
    await Promise.resolve()
    assert.equal(h.saved.length, 1)
    assert.equal(h.saved[0][0].word_boundary, 1)
    assert.equal(h.saved[0][0].start, 12)
    assert.equal(h.saved[0][0].subtitle_text, original.text)
    assert.deepEqual(h.props.subtitle, original)
})
