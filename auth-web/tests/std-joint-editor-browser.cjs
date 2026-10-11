const fs=require('fs'),path=require('path'),ts=require('typescript'),assert=require('node:assert/strict'),sharp=require('sharp'),{chromium}=require('@playwright/test');
const root=path.resolve(__dirname,'..');
async function main(){
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome'}), page=await browser.newPage({viewport:{width:1400,height:1000}});
 page.setDefaultTimeout(10000);
 const source=await sharp({create:{width:320,height:200,channels:3,background:'#ffcc88'}}).png().toBuffer();
 let saved=false;
 const region={id:'arm',name:'아래팔',polygon:[[.3,.1],[.5,.1],[.5,.7],[.3,.7]],anchor:[.35,.2],contour:'exact',occluded:true,action:'hold',amplitude:2,period:2,cycles:1,start:0,subtitleId:'s'};
 const scene={number:1,imageId:'image',duration:6,subtitles:[{id:'s',text:'시작',start:0,end:6}],layerDraft:{editorRegions:[{...region,id:'body',name:'몸통',occluded:false},region]}};
 await page.route('http://joint.test/**',async route=>{
  const req=route.request(),url=new URL(req.url());
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<html><body><div id="root"></div></body></html>'});
  if(url.searchParams.has('image'))return route.fulfill({contentType:'image/png',body:source});
  if(url.pathname.endsWith('region-layers')){
   if(req.method()==='POST'){assert.ok(req.postDataBuffer().includes(Buffer.from('image/png')));saved=true;return route.fulfill({json:{asset:{id:'drawn-part'}}});}
   return route.fulfill({json:{packages:[]}});
  }
  return route.fulfill({json:{scenes:[scene]}});
 });
 await page.goto('http://joint.test');
 await page.addScriptTag({path:path.join(path.dirname(require.resolve('react/package.json')),'umd/react.development.js')});
 await page.addScriptTag({path:path.join(path.dirname(require.resolve('react-dom/package.json')),'umd/react-dom.development.js')});
 const modules={'@/lib/stdRegionMotion':'lib/stdRegionMotion.ts','@/lib/stdRegionMotionCopy':'lib/stdRegionMotionCopy.ts','./StdRegionLayers':'components/StdRegionLayers.tsx',editor:'components/StdRegionMotionEditor.tsx'};
 let bundle=`var modules={},cache={};function require(name){if(name==='react')return React;if(name==='react-dom')return ReactDOM;if(name==='react/jsx-runtime')return {jsx:(t,p,k)=>React.createElement(t,{...p,key:k}),jsxs:(t,p,k)=>React.createElement(t,{...p,key:k}),Fragment:React.Fragment};if(cache[name])return cache[name];var exports={};cache[name]=exports;modules[name](exports,require);return exports;}\n`;
 for(const [key,file]of Object.entries(modules))bundle+=`modules[${JSON.stringify(key)}]=function(exports,require){${ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:1,target:9,jsx:4}}).outputText}};\n`;
 bundle+=`ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(require('editor').default,{projectId:'fixture',headers:{},locale:'ko'}));`;
 await page.evaluate(()=>{Object.defineProperty(window.crypto,'subtle',{value:{digest:async()=>new Uint8Array(32).buffer}})});
 await page.addScriptTag({content:bundle});
 await page.getByRole('button',{name:'영역 동작 지정',exact:true}).click();
 await page.getByRole('combobox',{name:'동작 영역',exact:true}).selectOption('1');
 await page.getByRole('combobox',{name:'부모 관절',exact:true}).selectOption('body');
 await page.getByRole('combobox',{name:'동작 종류',exact:true}).selectOption('walk');
 await page.getByRole('combobox',{name:'보행 부위',exact:true}).selectOption('lower');
 await page.getByRole('combobox',{name:'좌우 동작 위상',exact:true}).selectOption('0.5');
 await page.getByRole('button',{name:'부위 그리기 · 가려진 부분·관절 겹침 보완',exact:true}).click();
 const canvas=page.locator('canvas');await page.waitForFunction(()=>document.querySelector('canvas')?.width===320);
 const pixel=()=>canvas.evaluate(c=>Array.from(c.getContext('2d').getImageData(112,40,1,1).data));const before=await pixel();
 await page.getByLabel('부위 색상',{exact:true}).fill('#123456');
 await page.getByRole('button',{name:'관절 겹침 원 그리기',exact:true}).click();assert.deepEqual(await pixel(),[18,52,86,255]);
 await page.getByRole('button',{name:'되돌리기',exact:true}).click();assert.deepEqual(await pixel(),before);
 await page.getByRole('button',{name:'색칠',exact:true}).click();
 await canvas.evaluate(c=>{c.style.width='320px';c.style.height='200px'});await canvas.scrollIntoViewIfNeeded();
 const box=await canvas.boundingBox();await page.mouse.move(box.x+box.width*.35,box.y+box.height*.75);await page.mouse.down();await page.mouse.move(box.x+box.width*.35,box.y+box.height*.8,{steps:10});await page.mouse.up();
 assert.equal(await canvas.evaluate(c=>c.getContext('2d').getImageData(112,155,1,1).data[3]),255);
 await page.getByRole('button',{name:'수정한 외곽선 저장',exact:true}).click();await page.getByText('보완 이미지를 저장했습니다.',{exact:false}).waitFor();assert.equal(saved,true);
 assert.equal(await page.getByRole('combobox',{name:'부모 관절',exact:true}).inputValue(),'body');
 console.log('PASS: parent/gait settings, hidden-part drawing before preparation, overlap cap, undo, continuous brush, transparent PNG upload');await browser.close();
}
main().catch(e=>{console.error(e);process.exit(1)});
