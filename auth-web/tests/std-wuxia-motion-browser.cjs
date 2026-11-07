const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('@playwright/test'),esbuild=require('esbuild'),sharp=require('sharp');
const root=path.resolve(__dirname,'..'),out=path.resolve(root,'../output/wuxia-motion');fs.mkdirSync(out,{recursive:true});
const script=esbuild.buildSync({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import Preview from './components/StdWuxiaScenePreview';import Controls from './components/StdWuxiaMotionControls';
const state={asset_id:'a',sha256:'a'.repeat(64),media_url:'/art.png',start:0,end:1,face_exclusion_boxes:[[.3,.25,.65,.55]]};
const pkg={contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'S001',preview_duration_seconds:4,states:[state],graphics:[]}]};
function App(){const [value,set]=React.useState('none'),[time,setTime]=React.useState(0);window.demo=(v,t)=>{set(v);setTime(t);document.getElementById('title').textContent=v;};return <><div id="controls"><Controls key={value} value={value} busy={false} onSave={async v=>{await fetch('/api/std/projects/fixture/scene-effects',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_numbers:[1],field:'image_effect',value:v})});set(v)}}/></div><div id="screen"><Preview project={{project_payload:{structure:{wuxia_ae_package:pkg,scenes:[{scene_number:1,image_effect:value}]}}}} sceneNumber={1} subtitles={[]} seconds={time} headers={{}}/></div></>};createRoot(document.getElementById('root')).render(<App/>);`,resolveDir:root,loader:'tsx'},bundle:true,write:false,format:'iife',jsx:'automatic'}).outputFiles[0].text;
(async()=>{const browser=await chromium.launch({headless:true,channel:'chrome'});try{
 const page=await browser.newPage({viewport:{width:1200,height:850}}),errors=[],saves=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://localhost:43219/**',r=>{
  const name=new URL(r.request().url()).pathname;
  if(name==='/art.png')return r.fulfill({contentType:'image/png',body:fs.readFileSync(path.join(root,'public/img/styles/style_wuxia_webtoon.png'))});
  if(name.endsWith('/scene-effects')){saves.push(r.request().postDataJSON());return r.fulfill({json:{success:true}})}
  return r.fulfill({contentType:'text/html',body:`<style>body{margin:0;background:#101722;color:white;font:18px sans-serif}#screen{position:relative;width:960px;height:540px;margin-top:20px}#controls{height:220px;padding:10px}label{display:block;margin:8px}select,button{padding:8px;margin-left:10px}#title{height:40px}.absolute{position:absolute}.inset-0{inset:0}.h-full{height:100%}.w-full{width:100%}.object-cover{object-fit:cover}.overflow-hidden{overflow:hidden}.bg-black{background:black}.bg-white{background:white}</style><div id="title"></div><div id="root"></div>`});
 });
 await page.goto('http://localhost:43219');await page.addScriptTag({content:script});
 await page.getByLabel('무협 이동 방향').selectOption('pan_right');await page.getByLabel('무협 줌 방향').selectOption('zoom_out');await page.getByLabel('열기 아지랑이 왜곡').check();await page.getByRole('button',{name:'선택한 씬에 모션 적용'}).click();
 await page.waitForFunction(()=>document.querySelector('[data-wuxia-camera-clock]')?.getAttribute('style').includes('scale(1.24)'));
 assert.deepEqual(saves[0],{scene_numbers:[1],field:'image_effect',value:'pan_right_zoom_out+heat'});
 const show=async(kind,time)=>{await page.evaluate(([k,t])=>window.demo(k,t),[kind,time]);await page.locator('[data-wuxia-camera-clock]').waitFor();await page.waitForFunction(()=>document.querySelectorAll('#screen img').length>0&&[...document.querySelectorAll('#screen img')].every(i=>i.complete&&i.naturalWidth>0));await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));};
 await show('pan_right_zoom_out',0);const before=await page.locator('[data-wuxia-camera-clock]').getAttribute('style');await show('pan_right_zoom_out',1);assert.notEqual(await page.locator('[data-wuxia-camera-clock]').getAttribute('style'),before);await show('pan_right_zoom_out',0);assert.equal(await page.locator('[data-wuxia-camera-clock]').getAttribute('style'),before);
 await show('none+heat',.5);const a=await page.locator('#screen').screenshot();assert.ok(await page.locator('[data-wuxia-heat-band]').count()>5);
 await show('none+heat',.9);const b=await page.locator('#screen').screenshot();
 const crop=(buffer,top,height)=>sharp(buffer).extract({left:250,top,width:300,height}).raw().toBuffer();
 assert.equal((await crop(a,190,60)).equals(await crop(b,190,60)),true,'reviewed anatomy rows must remain unchanged');
 assert.equal((await crop(a,0,80)).equals(await crop(b,0,80)),false,'heat must deform the artwork independently of the camera');
 await page.screenshot({path:path.join(out,'controls-and-heat.png')});
 let frame=0;
 for(const kind of ['pan_right_zoom_in','pan_left_zoom_out','pan_up_zoom_in','pan_down_zoom_out','zoom_in','zoom_out','none+heat']){
  for(let i=0;i<(kind==='none+heat'?48:24);i++){await show(kind,i/24);await page.locator('#screen').screenshot({path:path.join(out,`frame-${String(frame++).padStart(4,'0')}.png`)});}
 }
 assert.deepEqual(errors,[]);console.log('PASS real controls save scene 1; four camera directions + zoom; spatial heat changes while protected face rows stay identical; '+out);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
