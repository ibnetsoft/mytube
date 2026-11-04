const fs=require('fs'),path=require('path');
const {chromium}=require(require.resolve('playwright',{paths:['C:/Users/kimse/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules']}));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1200},deviceScaleFactor:1});
 const errors=[],cancellations=[];page.on('pageerror',e=>errors.push(String(e)));page.on('requestfailed',r=>{const v=r.url()+': '+r.failure().errorText;(r.failure().errorText==='net::ERR_ABORTED'?cancellations:errors).push(v)});
 await page.goto('file:///'+path.join(__dirname,'motion-preview.html').replaceAll('\\','/'));
 await page.evaluate(()=>document.fonts.ready);
 const all=await page.evaluate(()=>preview.data.scenes);
 const results=[];let count=0;
 for(let i=0;i<all.length;i++){
  await page.evaluate(i=>preview.choose(i),i);
  for(let g=0;g<all[i].graphics.length;g++){
   const graphic=all[i].graphics[g];
   await page.evaluate(seconds=>preview.setTime(seconds),(graphic.preview_start+graphic.preview_end)/2*all[i].preview_duration_seconds);
   await page.evaluate(()=>new Promise((resolve,reject)=>{const im=new Image();im.onload=resolve;im.onerror=()=>reject(new Error('Missing art'));im.src=document.getElementById('art').getAttribute('href')}));
   const check=await page.evaluate(()=>{const svg=document.getElementById('graphics');return Array.from(svg.querySelectorAll('text')).map(e=>{const r=e.getBBox();return {text:e.textContent,box:[r.x,r.y,r.width,r.height],inside:r.x>=0&&r.y>=0&&r.x+r.width<=1920&&r.y+r.height<=1080}})});
   results.push({scene:i+1,graphic:g,check});
   await page.locator('#stage').screenshot({path:path.join(__dirname,'qa',`overlay-${String(++count).padStart(2,'0')}.png`)});
  }
 }
 await page.evaluate(()=>{preview.choose(25);preview.setTime(preview.data.scenes[25].preview_duration_seconds*.77)});
 await page.locator('#stage').screenshot({path:path.join(__dirname,'qa','final-climax.png')});
 const report={browser:'Edge headless',graphics_checked:results.length,font_checks:await page.evaluate(()=>['NotoSansKR','DoHyeon','BlackHanSans'].map(f=>[f,document.fonts.check('38px '+f)])),errors,rapid_scene_switch_request_cancellations:cancellations,overflows:results.filter(r=>r.check.some(c=>!c.inside)),missing_graphics:results.filter(r=>!r.check.length),results};
 fs.writeFileSync(path.join(__dirname,'preview-verification.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify({graphics:results.length,errors,overflows:report.overflows.length,missing:report.missing_graphics.length,fonts:report.font_checks}));
 await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
