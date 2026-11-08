/** Render an isolated real-scene QA project through the actual web component. */
const fs=require('fs'),path=require('path'),{createRequire}=require('module')
const root=path.resolve(__dirname,'..'),web=path.join(root,'auth-web'),req=createRequire(path.join(web,'package.json'))
async function main(){
 const dir=path.resolve(process.argv[2]),project=JSON.parse(fs.readFileSync(path.join(dir,'project.json'))),mapping=JSON.parse(fs.readFileSync(path.join(dir,'source-map.json')))
 const scene=project.project_payload.structure.wuxia_ae_package.scenes[0],duration=scene.preview_duration_seconds,fps=24
 const load=req('./tests/load-ts-module.cjs'),{freezeWuxiaScene}=load(path.join(web,'lib/stdWuxiaNative.ts'))
 const timeline=freezeWuxiaScene(project,1,[],0,duration,fps,{metadata:{}})
 fs.writeFileSync(path.join(dir,'probe-snapshot.json'),JSON.stringify({motion:{version:1,enabled:true,aspect:'16:9',fps,scenes:{},production_method:'ae'},scenes:[{number:1,start:0,end:duration,source_kind:'image',wuxia_timeline:timeline}]}))
 const browserProject=JSON.parse(JSON.stringify(project));for(const s of browserProject.project_payload.structure.wuxia_ae_package.scenes[0].states)s.media_url='data:image/png;base64,'+fs.readFileSync(mapping[s.media_url]).toString('base64')
 const js=await req('esbuild').build({absWorkingDir:web,stdin:{resolveDir:web,loader:'tsx',contents:`import React,{useState} from 'react';import{createRoot}from'react-dom/client';import{flushSync}from'react-dom';import Preview from './components/StdWuxiaScenePreview';const project=${JSON.stringify(browserProject)},headers={};function App(){const[t,setT]=useState(0);window.renderAt=n=>flushSync(()=>setT(n));return <><div id="stage" style={{position:'relative',width:1920,height:1080}}><Preview project={project} sceneNumber={1} subtitles={[]} seconds={t} headers={headers}/></div><input aria-label="time" type="range" min="0" max="${duration-1/fps}" step="${1/fps}" value={t} onChange={e=>setT(Number(e.target.value))}/><span>{t.toFixed(3)}s</span></>};createRoot(document.getElementById('app')).render(<App/>);`},bundle:true,jsx:'automatic',platform:'browser',format:'iife',write:false})
 const css='.absolute{position:absolute}.inset-0{inset:0}.w-full{width:100%}.h-full{height:100%}.object-cover{object-fit:cover}.overflow-hidden{overflow:hidden}.pointer-events-none{pointer-events:none}.bg-black{background:black}body{margin:0;background:#10141b;color:white}input{width:1600px}'
 fs.writeFileSync(path.join(dir,'preview.html'),`<!doctype html><meta charset="utf-8"><style>${css}</style><div id="app"></div><script>${js.outputFiles[0].text.replace(/<\/script/gi,'<\\/script')}</script>`)
 fs.mkdirSync(path.join(dir,'web-frames'),{recursive:true})
 const browser=await req('@playwright/test').chromium.launch({headless:true,channel:'chrome'})
 try{
 const page=await browser.newPage({viewport:{width:1920,height:1140},deviceScaleFactor:1});page.on('pageerror',e=>console.error(e.message))
 await page.route('https://sprite-qa.local/**',async route=>{
  const u=new URL(route.request().url()),file=mapping[u.pathname+u.search]
  if(u.pathname==='/preview')return route.fulfill({status:200,contentType:'text/html',body:fs.readFileSync(path.join(dir,'preview.html'))})
  if(file)return route.fulfill({status:200,contentType:'image/png',body:fs.readFileSync(file)})
  return route.abort()
 })
 await page.goto('https://sprite-qa.local/preview');await page.locator('[data-wuxia-effect-overlay]').waitFor({state:'visible'})
 for(let i=0;i<timeline.samples.length;i++){
  await page.evaluate(t=>window.renderAt(t),i/fps)
  const ambient=timeline.samples[i].ambient||[]
  if(ambient.length){
   for(const patch of ambient)await page.locator(`[data-ambient-frame="${patch.frame}"]`).waitFor({state:'visible'})
  }else if(await page.locator('[data-ambient-frame]').count())throw Error(`Unexpected ambient sprite at ${i}`)
  const count=await page.locator('[data-wuxia-effect-overlay] polygon').count(),expected=timeline.samples[i].effects?.overlays?.length||0
  if(count!==expected)throw Error(`Web and frozen native polygon mismatch at ${i}`)
  await page.locator('#stage').screenshot({path:path.join(dir,'web-frames',`frame-${String(i).padStart(3,'0')}.png`)})
 }
 }finally{await browser.close()}
 fs.writeFileSync(path.join(dir,'web-verification.json'),JSON.stringify({frames:timeline.samples.length,fps,source:'actual episode 1 scene 11 artwork',component:'StdWuxiaScenePreview',native_polygon_counts_equal:true,native_sprite_indices_equal:true,sprite_frames:timeline.samples.flatMap((s,i)=>s.ambient?.length?[i]:[]),actual_ae_output_checked:false},null,2))
 console.log('WEB_ACTUAL_SCENE_CAPTURED',timeline.samples.length)
}
main().catch(e=>{console.error(e);process.exit(1)})
