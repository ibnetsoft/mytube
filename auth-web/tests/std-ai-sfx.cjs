const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict')
const cueApi={}
new Function('exports',ts.transpile(fs.readFileSync('auth-web/lib/stdSfxCues.ts','utf8'),{module:1,target:7}))(cueApi)
const exportsObject={}
new Function('require','exports',ts.transpile(fs.readFileSync('auth-web/lib/stdAiSfx.ts','utf8'),{module:1,target:7}))(
    id=>id==='crypto'?require(id):id==='./stdSfxCues'?cueApi:{},exportsObject)
const {sfxSnapshot,mergeAiSfx}=exportsObject
const subs=[{id:'1',scene_number:1,text:'문을 열었다',start:0,end:3}]
assert.equal(sfxSnapshot(subs),sfxSnapshot([{...subs[0],start:10,end:13}]),'Retiming alone must not require a new AI analysis')
assert.notEqual(sfxSnapshot(subs),sfxSnapshot([{...subs[0],text:'문을 닫았다'}]))
const manual={id:'manual',scene_number:1,source:'manual'}
const deleted={id:'removed',scene_number:2,source:'manual',enabled:false,user_override:true}
const automatic={id:'old',scene_number:3,source:'codex-sfx-v1'}
const result=mergeAiSfx([manual,deleted,automatic],[1,2,3].map(n=>({id:'new'+n,scene_number:n,source:'codex-sfx-v1'})))
assert.deepEqual(result.map(c=>c.id),['manual','removed','new3'])
const route=fs.readFileSync('auth-web/app/api/std/projects/[projectId]/sfx-plan/route.ts','utf8')
assert(route.includes(".eq('employee_email', auth.requester.email)"))
assert(route.includes(".eq('updated_at', project.updated_at)"))
assert(route.includes('job.payload.snapshot !== snapshot'))
assert(!route.includes('/tts/'))
console.log('PASS: changed script invalidation, timing-only reuse, manual and deleted cue preservation, scoped/CAS apply')
