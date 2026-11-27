const assert = require('node:assert/strict')
const fs = require('node:fs')
const ts = require('typescript')
const out = {}
new Function('exports', ts.transpile(fs.readFileSync('auth-web/lib/stdReviewedPayloadImages.ts', 'utf8'), { module: 1, target: 7 }))(out)
const sha = 'a'.repeat(64)
const scene = { scene_number: 18, cut_id: 'C018', image_use_status: 'approved', source_image_sha256: sha, gcs_bucket: 'bucket', gcs_path: 'scene.png', anatomy_review: { contract: 'wuxia_anatomy_review/v1', verdict: 'pass', source_sha256: sha } }
const project = { id: 'p', project_payload: { structure: { scenes: [scene] } } }
const read = () => out.withReviewedPayloadImages(project, [])
assert.equal(read().length, 1)
scene.image_use_status = 'review_candidate'; assert.equal(read().length, 0)
scene.image_use_status = 'approved'; scene.anatomy_review.source_sha256 = 'b'.repeat(64); assert.equal(read().length, 0)
scene.anatomy_review.source_sha256 = sha; project.project_payload.structure.excluded_image_cut_ids = ['C018']; assert.equal(read().length, 0)
project.project_payload.structure.excluded_image_cut_ids = []; assert.equal(out.withReviewedPayloadImages(project, [{ asset_type: 'image', scene_number: 18 }]).length, 1)
console.log('PASS: only reviewed, current and non-excluded payload images are available')
