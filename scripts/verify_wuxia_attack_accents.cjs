// Local, isolated production-component verification. Never edits a registered episode.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),{createRequire}=require('module'),{spawnSync}=require('child_process')
const root=path.resolve(__dirname,'..'),web=path.join(root,'auth-web'),req=createRequire(path.join(web,'package.json'))
const out=path.resolve(process.argv[2]||path.join(root,'output/wuxia-attack-accents-preview'))
const python=process.env.WUXIA_TEST_PYTHON||path.join(root,'.venv-script/bin/python')
async function main(){
 fs.mkdirSync(out,{recursive:true})
 const art=spawnSync(python,['-c',`from PIL import Image,ImageDraw
import sys
im=Image.new('RGB',(1920,1080),'#162234');d=ImageDraw.Draw(im)
d.rectangle((190,108,540,360),fill='#263b54',outline='#526986',width=4)
d.text((220,210),'FACE / TEXT PROTECTED',fill='#cad6e6')
d.rounded_rectangle((1280,650,1490,860),radius=20,fill='#5a5f66',outline='#9eabb8',width=6)
d.line([(480,864),(960,778),(1344,702)],fill='#365c75',width=8)
d.text((950,940),'REVIEWED ATTACK DIRECTION -> CONTACT',fill='#a1b6c9')
im.save(sys.argv[1])`,path.join(out,'fixture.png')],{encoding:'utf8'});if(art.status)throw Error(art.stderr)
 const bytes=fs.readFileSync(path.join(out,'fixture.png')),sha=crypto.createHash('sha256').update(bytes).digest('hex')
 const state={asset_id:'fixture',sha256:sha,start:0,end:1,face_exclusion_boxes:[[.098,.1,.282,.334]],media_url:'data:image/png;base64,'+bytes.toString('base64')}
 const review={contract:'wuxia_attack_accent/v1',source_sha256:sha,source_reviewed:true,event:'technical fixture: charged strike on target',materials:'technical fixture stone target',reason:'verify ordered speed, contact flash and outward discharge',motion_evidence:'explicit technical trajectory; not production artwork approval',timing_basis:'scene_local',protected_boxes:state.face_exclusion_boxes,electricity_motivated:true,screen_flash_reviewed:true}
 const base={asset_id:'fixture',center:[.7,.65],attack_path:[[.25,.8],[.5,.72],[.7,.65]],intensity:1,radius:.65,contact_at_seconds:1,action_review:review}
 const effects=[{...base,type:'attack_speedline',duration_seconds:.25},{...base,type:'contact_flash',flash_scope:'screen',duration_seconds:2/24},{...base,type:'electric_discharge',duration_seconds:.5,delay_seconds:2/24}]
 const scene={scene_id:'DEMO_S01',preview_start_seconds:0,preview_duration_seconds:2,states:[state],graphics:[],effects}
 const project={id:'technical-fixture',project_payload:{render_settings:{motion:{fps:24}},structure:{image_style:'wuxia_webtoon',wuxia_ae_package:{contract:'wuxia_still_ae_episode/v1',scenes:[scene]}}}}
 const loader=req('./tests/load-ts-module.cjs'),{freezeWuxiaScene}=loader(path.join(web,'lib/stdWuxiaNative.ts'))
 const timeline=freezeWuxiaScene(project,1,[],0,2,24,{metadata:{sha256:sha,gcs_bucket:'fixture',gcs_path:'fixture.png'}})
 fs.writeFileSync(path.join(out,'frozen-timeline.json'),JSON.stringify(timeline))
 const bundle=await req('esbuild').build({absWorkingDir:web,stdin:{resolveDir:web,loader:'tsx',contents:`import React,{useState} from 'react';import{createRoot}from'react-dom/client';import{flushSync}from'react-dom';import Preview from './components/StdWuxiaScenePreview';const project=${JSON.stringify(project)},headers={};function App(){const[t,setT]=useState(0);window.renderAt=(n)=>flushSync(()=>setT(n));return <><div id="stage" style={{position:'relative',width:960,height:540}}><Preview project={project} sceneNumber={1} subtitles={[]} seconds={t} headers={headers}/></div><input aria-label="time" type="range" min="0" max="1.99" step="0.0416666667" value={t} onChange={e=>setT(Number(e.target.value))}/><span>{t.toFixed(3)}s</span></>};createRoot(document.getElementById('app')).render(<App/>);`},bundle:true,jsx:'automatic',platform:'browser',format:'iife',write:false})
 const css='.absolute{position:absolute}.inset-0{inset:0}.w-full{width:100%}.h-full{height:100%}.object-cover{object-fit:cover}.overflow-hidden{overflow:hidden}.pointer-events-none{pointer-events:none}.bg-black{background:black}body{margin:0;background:#0b1018;color:#ced9e8;font:14px sans-serif}h3,p{margin:12px}input{width:760px}#stage{margin:0}'
 const html=`<!doctype html><meta charset="utf-8"><style>${css}</style><h3>Attack accents — production web component / technical fixture</h3><p>0.75–1s directional travel · 1s contact flash · then white/yellow discharge. Not an episode or AE output.</p><div id="app"></div><script>${bundle.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')}</script>`
 fs.writeFileSync(path.join(out,'preview.html'),html)
 const browser=await req('@playwright/test').chromium.launch({headless:true,channel:'chrome'})
 try{
  const page=await browser.newPage({viewport:{width:960,height:650}})
  page.on('pageerror',error=>console.error('preview:',error.message))
  await page.goto('file://'+path.join(out,'preview.html'))
  await page.locator('[data-wuxia-effect-overlay]').waitFor({state:'visible'})
  for(let i=0;i<48;i++){
   await page.evaluate(t=>window.renderAt(t),i/24)
   const actual=await page.locator('[data-wuxia-effect-overlay] polygon').count(),expected=timeline.samples[i].effects?.overlays?.length||0
   if(actual!==expected)throw Error(`Frame ${i}: actual component ${actual}, frozen AE ${expected}`)
   await page.locator('#stage').screenshot({path:path.join(out,`frame-${String(i).padStart(3,'0')}.png`)})
  }
 }finally{await browser.close()}
 const check=spawnSync(python,['-c',`import sys,json
sys.path.insert(0,sys.argv[1])
from wuxia_effects import validate_samples
from wuxia_native_timeline import jsx
t=json.load(open(sys.argv[2]));validate_samples(t)
for s in t['states']:s.update(file='fixture.png',ambient_runtime=[],mouth_runtime=[])
a,b=jsx(t,2,24);j=json.loads(a.split('var WT=',1)[1].split(';\\n',1)[0]);assert [f['overlays'] for f in j['effect_samples']]==[f.get('effects',{}).get('overlays',[]) for f in t['samples']]
open(sys.argv[3],'w').write(a+b)
`,path.join(root,'worker'),path.join(out,'frozen-timeline.json'),path.join(out,'native-effect-snippet.jsx')],{encoding:'utf8'})
 if(check.status)throw Error(check.stderr)
 fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({production_component_frames:48,web_frozen_native_vectors_equal:true,actual_ae_render_verified:false,source:'technical fixture',fps:24},null,2))
 console.log(out)
}
main().catch(e=>{console.error(e);process.exit(1)})
