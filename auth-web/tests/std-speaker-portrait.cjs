const assert = require('node:assert/strict')
const test = require('node:test')
const { speakerPortraitStyle } = require('./load-ts.cjs')(require('node:path').join(__dirname, '../lib/stdSpeakerPortrait.ts'))

test('verified image crops select one face and unknown images are never assigned another character crop', () => {
    const style = speakerPortraitStyle({ thumbnail_draft_metadata: { sha256: 'ea44a9ec300cb26798a086e35f68401f7b46a2533473db83d470c1a2274e8217' } })
    assert.equal(style.position, 'absolute')
    assert(Math.abs(parseFloat(style.left) + 405 / 350 * 100) < 0.0001)
    assert.equal(speakerPortraitStyle({ thumbnail_draft_metadata: { sha256: 'other' } }), undefined)
    assert.equal(speakerPortraitStyle({ name: '志乃' }), undefined)
})


test('native detection crops the largest observed face without inventing one when unavailable', async () => {
    const { detectSpeakerPortrait } = require('./load-ts.cjs')(require('node:path').join(__dirname, '../lib/stdSpeakerPortrait.ts'))
    const image = { naturalWidth: 1000, naturalHeight: 800, src: '/face-fixture', isConnected: true, style: {} }
    global.window = { FaceDetector: class { async detect() { return [{ boundingBox: { x: 400, y: 100, width: 200, height: 220 } }] } } }
    try {
        detectSpeakerPortrait(image, {})
        await new Promise(resolve => setImmediate(resolve))
        assert.equal(image.style.position, 'absolute')
        assert(Number.parseFloat(image.style.width) > 100)
        const unknown = { ...image, src: '/unknown-fixture', style: {} }
        delete global.window.FaceDetector
        detectSpeakerPortrait(unknown, {})
        assert.deepEqual(unknown.style, {})
    } finally { delete global.window }
})
