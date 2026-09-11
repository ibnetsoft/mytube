import assert from 'node:assert/strict'
import { persistentThumbnailUrl } from '../lib/stdThumbnailUrl'

assert.equal(persistentThumbnailUrl('blob:https://studio.airing.work/expired', '/api/std/projects/test/assets/file?assetId=valid'), '/api/std/projects/test/assets/file?assetId=valid')
assert.equal(persistentThumbnailUrl('blob:expired', 'data:image/png;base64,abc', 'https://example.com/saved.png'), 'https://example.com/saved.png')
assert.equal(persistentThumbnailUrl('blob:expired', null, undefined), '')
assert.equal(persistentThumbnailUrl('javascript:alert(1)', '//external.test/x'), '')
assert.equal(persistentThumbnailUrl('/raw-background.png', '/flattened-thumbnail.png'), '/raw-background.png')
console.log('thumbnail persistent URL tests passed')
