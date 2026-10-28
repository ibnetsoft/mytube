const fs=require('node:fs'),path=require('node:path'),rt=require('../scripts/std_web_runtime.cjs'),{chromium}=rt.load?require('../auth-web/node_modules/@playwright/test'):{}, {bundle}=require('../auth-web/tests/std-web-motion-browser.cjs')
const web=rt.web,out=path.join(rt.root,'output/motion-native-comparison')
async function main(){const browser=await chromium.launch({headless:true,channel:'chrome'}),page=await browser.newPage();try{
 await page.route('http://localhost:43200/**',r=>{const url=new URL(r.request().url());if(url.pathname==='/reference.psd')return r.fulfill({body:fs.readFileSync(path.join(rt.root,'output/ae-psd-wuxia-3285/wuxia-split-layered.psd')),contentType:'image/vnd.adobe.photoshop'});if(url.pathname==='/ae.png')return r.fulfill({body:fs.readFileSync(path.join(out,'ae-1.png')),contentType:'image/png'});return r.fulfill({body:'<html></html>',contentType:'text/html'})});await page.goto('http://localhost:43200')
 await page.addScriptTag({path:path.join(web,'node_modules/react/umd/react.development.js')});await page.addScriptTag({path:path.join(web,'node_modules/react-dom/umd/react-dom.development.js')});await page.addScriptTag({content:bundle(['lib/stdWebMotion.ts','node_modules/ag-psd/index.js','components/StdWebMotionStudio.tsx','components/StdProductionMethodSelector.tsx','lib/stdMotionStudio.ts','components/StdMotionStudio.tsx'].map(p=>path.join(web,p)))})
 const test=fs.readFileSync(path.join(web,'tests/std-motion-advanced-browser.cjs'),'utf8'),setup=test.split('const frames=await page.evaluate(async()=>{')[1].split('const original=window.advanced.renderAdvancedLayer')[0]
 const result=await page.evaluate('(async()=>{'+setup+`
 const aeCanvas=document.createElement('canvas');aeCanvas.width=1920;aeCanvas.height=1080;aeCanvas.getContext('2d').drawImage(await createImageBitmap(await (await fetch('/ae.png')).blob()),0,0);const ref=aeCanvas.getContext('2d').getImageData(220,540,400,300).data,candidates=[];
 for(const blur of [0,2,5,10,15,20])for(const amount of [0,10,20,35,50,75,100]){
  scene.layers.pulse.advanced={effects:[{type:'glow',amount,radius:10/1080,seed:0,keys:[{t:0,value:1},{t:1,value:1}],glow:{threshold:0,softKnee:0,basedOn:'alpha'}},{type:'blur',amount:100,radius:Math.max(.001,blur/1080),seed:0,keys:[{t:0,value:blur?1:0},{t:1,value:blur?1:0}]}]};motion.drawWebMotion(c,art,scene,.5);const pixels=c.getContext('2d').getImageData(220,540,400,300).data;let error=0;for(let i=0;i<pixels.length;i++)if(i%4!==3)error+=Math.abs(pixels[i]-ref[i]);candidates.push({blur,amount,mae:error/360000})
 }
 return candidates.sort((a,b)=>a.mae-b.mae)
})()`)
 fs.writeFileSync(path.join(out,'glow-calibration.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result.slice(0,12),null,2))
}finally{await browser.close()}}main().catch(e=>{console.error(e.message);process.exitCode=1})
