const test=require('node:test'),assert=require('node:assert/strict'),load=require('./load-ts-module.cjs'),{spawnSync}=require('node:child_process'),path=require('node:path')
const {wuxiaEffectFrame}=load('lib/stdWuxiaEffects.ts'),{freezeWuxiaScene}=load('lib/stdWuxiaNative.ts')
const sha='a'.repeat(64),state={asset_id:'art',sha256:sha,start:0,end:1,face_exclusion_boxes:[[.1,.1,.3,.3]],media_url:'/api/std/assets/gcs-file?bucket=test&path=art.png'}
const review={contract:'wuxia_attack_accent/v1',source_sha256:sha,source_reviewed:true,event:'charged palm contacts a stone target',materials:'stone',reason:'electrical skill release at contact',motion_evidence:'reviewed palm trajectory and contact pose',timing_basis:'scene_local',protected_boxes:[[.1,.1,.3,.3]],electricity_motivated:true,screen_flash_reviewed:true}
const effect=type=>({type,asset_id:'art',center:[.7,.65],attack_path:[[.25,.8],[.5,.72],[.7,.65]],duration_seconds:type==='contact_flash'?.083333333333:type==='attack_speedline'?.25:.5,intensity:1,radius:.4,contact_at_seconds:1,action_review:review,...(type==='contact_flash'?{flash_scope:'screen'}:{})})
const at=(effects,t,s=state)=>wuxiaEffectFrame({effects},s,[],t,0,2,()=>null,24)
test('directional trails lead contact, discharge and yellow flash start at contact, and all stop',()=>{
 assert(at([effect('attack_speedline')],.875).overlays.length)
 for(const type of ['electric_discharge','contact_flash'])assert.equal(at([effect(type)],.875).overlays.length,0)
 assert.equal(at([effect('attack_speedline')],1).overlays.length,0)
 for(const type of ['electric_discharge','contact_flash'])assert(at([effect(type)],1).overlays.length)
 assert.equal(at([effect('electric_discharge')],1.5).overlays.length,0)
 assert.equal(at([effect('electric_discharge')],1.1,{...state,asset_id:'cut'}).overlays.length,0)
})
test('bold white/yellow branching is deterministic on pause/seek and flickers on a frozen frame clock',()=>{
 const a=at([effect('electric_discharge')],1.125),b=at([effect('electric_discharge')],1.25)
 assert.deepEqual(a,at([effect('electric_discharge')],1.125));assert.notDeepEqual(a.overlays,b.overlays)
 assert.deepEqual(new Set(a.overlays.map(x=>x.color)),new Set(['#fff000','#ffffff']))
 assert(a.overlays.some(x=>Math.abs(x.points[0][0]-x.points[3][0])>6||Math.abs(x.points[0][1]-x.points[3][1])>6))
 assert(a.overlays.length<=96)
})
test('missing/stale source review, unsupported electricity, zero path and excessive flash fail closed',()=>{
 for(const patch of [{action_review:{...review,source_sha256:'b'.repeat(64)}},{action_review:{...review,electricity_motivated:false}},{attack_path:[[.7,.65],[.7,.65]]}])assert(at([{...effect('electric_discharge'),...patch}],1.1).issues.length)
 assert(at([{...effect('contact_flash'),duration_seconds:.5}],1).issues.length)
 assert(at([{...effect('attack_speedline'),delay_seconds:.1}],.875).issues.length)
 assert.equal(at([effect('electric_discharge')],1.1,{...state,energy_only_motion:true}).overlays.length,0)
})
test('native frozen vectors match the exact web frames, pass worker validation and survive AE JSX serialization',()=>{
 const effects=[effect('attack_speedline'),effect('electric_discharge'),{...effect('contact_flash'),flash_scope:'local'}]
 const scene={scene_id:'E99_S01',preview_start_seconds:0,preview_duration_seconds:2,states:[state],graphics:[],effects}
 const project={project_payload:{structure:{image_style:'wuxia_webtoon',wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[scene]}}}}
 const frozen=freezeWuxiaScene(project,1,[],0,2,24,{metadata:{}})
 for(const sample of frozen.samples){const web=at(effects,sample.at);assert.deepEqual(sample.effects,web.active.length?web:{})}
 const script=`import sys,json\nsys.path.insert(0,'../worker')\nfrom wuxia_effects import validate_samples\nfrom wuxia_native_timeline import jsx\nt=json.load(sys.stdin)\nvalidate_samples(t)\nfor s in t['states']:s.update(file='art.png',ambient_runtime=[],mouth_runtime=[])\na,b=jsx(t,2,24)\ndata=json.loads(a.split('var WT=',1)[1].split(';\\n',1)[0])\nassert [f['overlays'] for f in data['effect_samples']]==[f.get('effects',{}).get('overlays',[]) for f in t['samples']]\nprint('validated 48 identical web/native frames')`
 const r=spawnSync(process.env.WUXIA_TEST_PYTHON||'python3',['-c',script],{input:JSON.stringify(frozen),encoding:'utf8'})
 assert.equal(r.status,0,r.stderr);assert.match(r.stdout,/48 identical/)
})

test('two-frame delayed discharge ends on the identical exclusive web/native frame',()=>{
 const e={...effect('electric_discharge'),delay_seconds:2/24}
 const frames=Array.from({length:48},(_,i)=>at([e],i/24))
 assert.deepEqual(frames.flatMap((f,i)=>f.active.length?[i]:[]),Array.from({length:12},(_,i)=>i+26))
})

test('a protected contact cannot emit disconnected remote bolt fragments',()=>{
 const e={...effect('electric_discharge'),action_review:{...review,protected_boxes:[[.69,.64,.71,.66]]}}
 assert.equal(at([e],1.25).overlays.length,0)
})
