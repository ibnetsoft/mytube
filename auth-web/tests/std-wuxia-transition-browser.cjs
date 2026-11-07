const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('@playwright/test'),esbuild=require('esbuild');
const root=path.resolve(__dirname,'..'),out=path.resolve(root,'../output/wuxia-transitions');fs.mkdirSync(out,{recursive:true});
const script=esbuild.buildSync({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import Preview from './components/StdWuxiaScenePreview';
const state=(id)=>({asset_id:id,sha256:id.repeat(64),media_url:'/art-'+id+'.png',start:0,end:1});
const pkg={contract:'wuxia_still_ae_episode/v1',scenes:[{scene_id:'S001',preview_duration_seconds:2,states:[state('a')],graphics:[]},{scene_id:'S002',preview_duration_seconds:2,states:[state('b')],graphics:[]}]};
const root=createRoot(document.getElementById('screen'));window.demo=(kind,time)=>{root.render(<Preview project={{project_payload:{structure:{wuxia_ae_package:pkg,scenes:[{scene_number:2,transition_effect:kind}]}}}} sceneNumber={2} subtitles={[]} seconds={time} headers={{}}/>);document.getElementById('title').textContent=kind;};`,resolveDir:root,loader:'tsx'},bundle:true,write:false,format:'iife',jsx:'automatic'}).outputFiles[0].text;
(async()=>{const browser=await chromium.launch({headless:true,channel:'chrome'});try{
 const page=await browser.newPage({viewport:{width:960,height:600}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://localhost:43218/**',r=>{
  const name=new URL(r.request().url()).pathname;
  if(name==='/art-a.png')return r.fulfill({contentType:'image/png',body:fs.readFileSync(path.resolve(root,'public/img/styles/style_korean_webtoon.png'))});
  if(name==='/art-b.png')return r.fulfill({contentType:'image/png',body:fs.readFileSync(path.resolve(root,'public/img/styles/style_wuxia_webtoon.png'))});
  return r.fulfill({contentType:'text/html',body:`<style>body{margin:0;background:#101722;color:white;font:20px sans-serif}#screen{position:relative;width:960px;height:540px}#title{height:60px;display:flex;align-items:center;padding-left:20px}.absolute{position:absolute}.inset-0{inset:0}.h-full{height:100%}.w-full{width:100%}.object-cover{object-fit:cover}.overflow-hidden{overflow:hidden}.bg-black{background:black}.bg-white{background:white}</style><div id="title"></div><div id="screen"></div>`});
 });
 await page.goto('http://localhost:43218');await page.addScriptTag({content:script});
 const show=async(kind,time)=>{await page.evaluate(([k,t])=>window.demo(k,t),[kind,time]);await page.locator('[data-wuxia-transition]').waitFor();await page.waitForFunction(()=>document.querySelectorAll('#screen img').length>0&&[...document.querySelectorAll('#screen img')].every(i=>i.complete&&i.naturalWidth>0));await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));};
 await show('wipe_left',2);assert.match(await page.locator('[data-wuxia-transition]>div').first().getAttribute('style'),/translate\(100%/);
 await show('wipe_left',2.125);const before=await page.locator('[data-wuxia-transition]>div').first().getAttribute('style');
 await show('wipe_left',3);await show('wipe_left',2.125);assert.equal(await page.locator('[data-wuxia-transition]>div').first().getAttribute('style'),before);
 await show('flash',2);assert.equal(await page.locator('[data-wuxia-transition-flash]').count(),1);
 await show('flash',2.5);assert.equal(await page.locator('[data-wuxia-transition-flash]').count(),0);
 let frameNumber=0;
 for(const kind of ['wipe_left','wipe_up','flash','punch','snap_shake','dissolve','fade_out']){
  for(let i=0;i<24;i++){await show(kind,(kind==='fade_out'?3:2)+i/24);await page.screenshot({path:path.join(out,`frame-${String(frameNumber++).padStart(4,'0')}.png`)});}
 }
 assert.deepEqual(errors,[]);console.log('PASS real Wuxia preview: slide/backdrop, flash, pause/seek and seven effect frame sequences; '+out);
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
