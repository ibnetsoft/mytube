const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),ts=require('typescript'),{chromium}=require('@playwright/test')
const root=path.resolve(__dirname,'..'),trial=path.resolve(root,'../output/motion2d-research/wuxia-trial')
async function main(){
 const browser=await chromium.launch({headless:true,channel:'chrome'}),page=await browser.newPage({viewport:{width:1200,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));let saved=0,bytes=0
 try{
  const sharp=require('sharp'),actual=fs.existsSync(path.join(trial,'base.png'))&&fs.existsSync(path.join(trial,'closed.png'))
  const base=actual?fs.readFileSync(path.join(trial,'base.png')):await sharp({create:{width:836,height:470,channels:3,background:'#ffffff'}}).png().toBuffer()
  const closed=actual?fs.readFileSync(path.join(trial,'closed.png')):await sharp({create:{width:836,height:470,channels:4,background:{r:0,g:0,b:0,alpha:0}}}).composite([{input:await sharp({create:{width:30,height:30,channels:4,background:'#000000'}}).png().toBuffer(),left:440,top:280}]).png().toBuffer()
  await page.route('http://localhost:43188/**',async route=>{const u=new URL(route.request().url());if(u.pathname.endsWith('/motion2d-patches')){if(route.request().method()==='POST'){const body=route.request().postDataBuffer();assert(body.includes(Buffer.from('mouth_closed')));bytes=body.length;saved++;return route.fulfill({json:{patch:{id:'patch-1',role:'mouth_closed',sha256:'b'.repeat(64),created_at:'2026-11-12'}}})}return route.fulfill({json:{patches:[]}})}if(u.pathname==='/base.png')return route.fulfill({contentType:'image/png',body:base});return route.fulfill({contentType:'text/html',body:'<div id="root"></div>'})})
  await page.goto('http://localhost:43188/');for(const f of ['react/umd/react.development.js','react-dom/umd/react-dom.development.js'])await page.addScriptTag({path:path.join(root,'node_modules',f)})
  const code=ts.transpileModule(fs.readFileSync(path.join(root,'components/StdMotion2dPatches.tsx'),'utf8'),{compilerOptions:{module:1,target:9,jsx:4}}).outputText
  await page.addScriptTag({content:`var module={exports:{}};var exports=module.exports;var require=n=>n==='react'?React:n==='react/jsx-runtime'?{jsx:(t,p,k)=>React.createElement(t,{...p,key:k}),jsxs:(t,p,k)=>React.createElement(t,{...p,key:k}),Fragment:React.Fragment}:null;${code};window.PatchEditor=module.exports.default;`})
  await page.evaluate(()=>ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(PatchEditor,{projectId:'p',headers:{},scene:1,imageId:'img',imageSha:'a'.repeat(64),image:'/base.png',disabled:false})))
  await page.getByLabel('2D 패치 이미지').setInputFiles({name:'closed.png',mimeType:'image/png',buffer:closed})
  const canvas=page.getByLabel('패치 마스크 편집');await canvas.waitFor();await page.waitForFunction(()=>document.querySelector('canvas')?.width===836)
  const before=await canvas.evaluate(c=>c.getContext('2d').getImageData(455,295,1,1).data[3]);assert(before>0)
  if(actual)await page.screenshot({path:path.join(trial,'patch-editor.png'),fullPage:true})
  const box=await canvas.boundingBox();await page.mouse.click(box.x+455/836*box.width,box.y+295/470*box.height)
  const after=await canvas.evaluate(c=>c.getContext('2d').getImageData(455,295,1,1).data[3]);assert.equal(after,0)
  await page.getByRole('button',{name:'되돌리기',exact:true}).click();assert.equal(await canvas.evaluate(c=>c.getContext('2d').getImageData(455,295,1,1).data[3]),before)
  await page.getByRole('button',{name:'현재 패치 저장'}).click();await page.getByText('수정한 패치를 현재 씬 원본에 연결해 저장했습니다.').waitFor();assert.equal(saved,1);assert(bytes>100);assert.deepEqual(errors,[])
  const mask=await sharp(closed).extractChannel('alpha').png().toBuffer()
  await page.getByLabel('2D 마스크 이미지').setInputFiles({name:'candidate.png',mimeType:'image/png',buffer:mask});await canvas.waitFor();await page.waitForFunction(()=>document.querySelector('canvas')?.width===836);assert.equal(await canvas.evaluate(c=>c.getContext('2d').getImageData(0,0,1,1).data[3]),0);assert((await canvas.evaluate(c=>c.getContext('2d').getImageData(455,295,1,1).data[3]))>0)
  await page.getByRole('button',{name:'현재 패치 저장'}).click();await page.waitForFunction(()=>!document.querySelector('canvas'));assert.equal(saved,2)
  console.log(`PASS ${actual?'actual wuxia scene':'synthetic fixture'}: patch and grayscale mask import, erase, undo, and registration requests`)
 }finally{await browser.close()}
}main().catch(e=>{console.error(e);process.exitCode=1})
