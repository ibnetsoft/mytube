const assert = require('node:assert/strict'), fs = require('node:fs'), cp = require('node:child_process'), ts = require('typescript')
const load = require('./load-ts.cjs')
const {preserveAudioAnchors} = load('auth-web/lib/stdAudioAnchors.ts')
const {resolveSfxCues,sfxNeedsReview} = load('auth-web/lib/stdSfxCues.ts')
const {backgroundWindow} = load('auth-web/lib/stdAudioMix.ts')
const queue = fs.readFileSync('auth-web/lib/stdRenderQueue.ts','utf8')
const source = queue.slice(queue.indexOf('function buildRenderSubtitles('),queue.indexOf('function sentenceComplete('))
const renderRows = new Function('subtitleGain', ts.transpile(source+'\nreturn buildRenderSubtitles',{module:1,target:7}))(()=>1)
const row = (id,text,start,end,scene_number=2)=>({id,text,start,end,scene_number})
const before = [row('lead','이전 씬',0,10,1),row('door','문을 두드렸다',10,14),row('wait','기다렸다',14,18)]
const original = {subtitles:before,render_settings:{bgm_start_scene:2,bgm_start_subtitle:2,bgm_end_scene:2,bgm_start:1,bgm_end:2,
  sfx_cues:[{id:'sound',subtitle_id:'door',subtitle_text:'문을 두드렸다',scene_number:2,subtitle_index:1,word_boundary:1,start:1}]}}
const cases = [
  {name:'split and inserted captions',rows:[row('x','새 앞부분',0,20,1),row('d1','문을',20,23),row('d2','두드렸다',23,26),row('wait','기다렸다',26,30)],sfx:23,bgm:26},
  {name:'merge',rows:[row('merged','문을 두드렸다 기다렸다',30,45)],sfx:35,bgm:40},
  {name:'voice duration changed',rows:[row('door','문을 두드렸다',100,112),row('wait','기다렸다',112,124)],sfx:106,bgm:112},
  {name:'unrelated scene edit',rows:[row('new','완전히 바뀐 앞 씬',0,40,1),row('door','문을 두드렸다',40,46),row('wait','기다렸다',46,50)],sfx:43,bgm:46},
]
const python = `import ast,json,re,sys
from services.sfx_timing import retime_sfx_cues
from services.bgm_timeline import retime_bgm_settings
from pathlib import Path
tree=ast.parse(Path('services/remote_render_service.py').read_text(encoding='utf-8-sig'))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_sanitize_subtitles_for_render')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<sanitize>','exec'))
d=json.load(sys.stdin); rows=_sanitize_subtitles_for_render(d['rows'])
print(json.dumps({'sfx':retime_sfx_cues(d['cues'],rows,strict=True),'bgm':retime_bgm_settings(d['settings'],rows,130)}))`
for(const test of cases){
  const next=preserveAudioAnchors(original,{...original,subtitles:test.rows})
  const settings=next.render_settings, rows=renderRows({project_payload:{subtitles:test.rows}},[])
  assert.equal(rows[0].id,test.rows[0].id,'render export retains subtitle identity')
  const cues=resolveSfxCues(settings.sfx_cues,before)
  assert.equal(resolveSfxCues(cues,rows)[0].start,test.sfx,test.name)
  assert.equal(backgroundWindow(settings,rows,130).start,test.bgm,test.name)
  const worker=cp.spawnSync('python',['-X','utf8','-c',python],{input:JSON.stringify({rows,cues,settings}),encoding:'utf8'})
  assert.equal(worker.status,0,worker.stderr)
  const actual=JSON.parse(worker.stdout)
  assert.equal(actual.sfx[0].start,test.sfx,test.name+' worker')
  assert.equal(actual.bgm.bgm_start,test.bgm,test.name+' worker BGM')
  assert.equal(actual.bgm.bgm_end,test.rows.filter(r=>r.scene_number===2).at(-1).end)
}
const anchored=preserveAudioAnchors(original,original)
const deleted=[row('wait','기다렸다',26,30)]
assert(sfxNeedsReview(anchored.render_settings.sfx_cues[0],deleted),'deleted sound anchor must require review')
assert.equal(backgroundWindow(anchored.render_settings,deleted,130).start,26,'unaffected BGM identity survives another deletion')
const blank={...original,subtitles:[before[1],row('blank','',14,16),before[2]],render_settings:{...original.render_settings,bgm_start_subtitle:3}}
assert.equal(backgroundWindow(preserveAudioAnchors(blank,blank).render_settings,deleted,130).start,26)
const moved=preserveAudioAnchors(anchored,{...anchored,render_settings:{...anchored.render_settings,bgm_start_subtitle:1}})
assert.equal(backgroundWindow(moved.render_settings,before,130).start,10,'explicit new selection replaces old anchor')
assert.deepEqual(original.render_settings.sfx_cues[0].start,1,'capture must not mutate saved state')
const jpBefore=[row('ja','お鈴が戸へ向かい、',10,14),row('jb','戸を叩きました。',14,18)]
const jpAfter=[row('merged-ja',jpBefore.map(r=>r.text).join(''),30,50)]
const jp={subtitles:jpBefore,render_settings:{bgm_start_scene:2,bgm_start_subtitle:2,bgm_end_scene:2,sfx_cues:[{id:'knock',subtitle_id:'jb',subtitle_text:jpBefore[1].text,scene_number:2,word_boundary:0,subtitle_index:1}]}}
const js=preserveAudioAnchors(jp,{...jp,subtitles:jpAfter}).render_settings
const expectedJapanese=30+20*Array.from(jpBefore[0].text).length/Array.from(jpAfter[0].text).length
const jc=resolveSfxCues(js.sfx_cues,jpBefore)
assert.equal(resolveSfxCues(jc,jpAfter)[0].start,expectedJapanese)
const jw=cp.spawnSync('python',['-X','utf8','-c',python],{input:JSON.stringify({rows:renderRows({project_payload:{subtitles:jpAfter}},[]),cues:jc,settings:js}),encoding:'utf8'})
assert.equal(jw.status,0,jw.stderr);assert.equal(JSON.parse(jw.stdout).sfx[0].start,expectedJapanese)
console.log('PASS: web save → render export → worker sanitize → final audio retiming; split/merge/insertion/deletion/voice duration/blank rows/reselection')
