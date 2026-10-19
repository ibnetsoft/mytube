const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),ts=require('typescript'),{chromium}=require('@playwright/test')
const root=path.resolve(__dirname,'..')
function bundle(entries){
 const modules=new Map()
 function add(file){file=require.resolve(file);if(modules.has(file))return file;modules.set(file,'')
  let code=fs.readFileSync(file,'utf8');if(file.endsWith('.json'))code='module.exports='+code
  if(/\.tsx?$/.test(file))code=ts.transpileModule(code,{compilerOptions:{module:1,target:9,jsx:4}}).outputText
  const dependencies={}
  for(const match of code.matchAll(/require\(["']([^"']+)["']\)/g)){
   const name=match[1];if(name==='react'||name==='react/jsx-runtime'||name==='next/dynamic')continue
   if(name.startsWith('node:')||['fs','path','stream','util','zlib'].includes(name))continue
   const base=name.startsWith('@/')?path.join(root,name.slice(2)):name.startsWith('.')?path.resolve(path.dirname(file),name):null
   const resolved=name==='mediabunny'?path.join(root,'node_modules/mediabunny/dist/bundles/mediabunny.cjs'):base?['','.ts','.tsx','.js','/index.js'].map(ext=>base+ext).find(p=>fs.existsSync(p)&&fs.statSync(p).isFile()):require.resolve(name,{paths:[path.dirname(file)]});dependencies[name]=add(resolved)
  }
  modules.set(file,`function(module,exports,load){const ids=${JSON.stringify(dependencies)};const require=name=>name==='react'?React:name==='next/dynamic'?{default:()=>props=>React.createElement(window.Editor,props)}:name==='react/jsx-runtime'?{jsx:(t,p,k)=>React.createElement(t,{...p,key:k}),jsxs:(t,p,k)=>React.createElement(t,{...p,key:k}),Fragment:React.Fragment}:load(ids[name]);\n${code}\n}`);return file
 }
 const ids=entries.map(add)
 return `var process={env:{NODE_ENV:'test'}};var registry={${[...modules].map(([k,v])=>JSON.stringify(k)+':'+v).join(',')}},cache={};function load(id){if(!id)throw Error('Unsupported test module');if(cache[id])return cache[id].exports;const module={exports:{}};cache[id]=module;registry[id](module,module.exports,load);return module.exports};window.motion=load(${JSON.stringify(ids[0])});window.psd=load(${JSON.stringify(ids[1])});window.Editor=load(${JSON.stringify(ids[2])}).default;window.Selector=load(${JSON.stringify(ids[3])}).default;window.motionSettings=load(${JSON.stringify(ids[4])});window.Production=load(${JSON.stringify(ids[5])}).default;`
}
async function main(){
 const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'}),page=await browser.newPage({viewport:{width:1400,height:1000}})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 try{
  await page.route('http://localhost:43199/**',r=>r.fulfill({contentType:'text/html',body:'<html><body><div id="root"></div></body></html>'}));await page.goto('http://localhost:43199')
  await page.addScriptTag({path:path.join(root,'node_modules/react/umd/react.development.js')});await page.addScriptTag({path:path.join(root,'node_modules/react-dom/umd/react-dom.development.js')})
  await page.addScriptTag({content:bundle([path.join(root,'lib/stdWebMotion.ts'),path.join(root,'node_modules/ag-psd/index.js'),path.join(root,'components/StdWebMotionStudio.tsx'),path.join(root,'components/StdProductionMethodSelector.tsx'),path.join(root,'lib/stdMotionStudio.ts'),path.join(root,'components/StdMotionStudio.tsx')])})
  const evidence=await page.evaluate(async()=>{
   const {motion,psd}=window,make=(w,h,color)=>{const c=document.createElement('canvas');c.width=w;c.height=h;c.getContext('2d').fillStyle=color;c.getContext('2d').fillRect(0,0,w,h);return c}
   // A document-positioned mask reveals only half the subject. It must travel
   // with the subject and preserve grayscale alpha, not just the saved composite.
   const mask=make(20,20,'white');mask.getContext('2d').fillStyle='#808080';mask.getContext('2d').fillRect(10,0,10,20)
   const maskedComposite=make(320,180,'blue'),mctx=maskedComposite.getContext('2d');mctx.fillStyle='red';mctx.fillRect(100,50,10,20);mctx.fillStyle='rgb(128,0,127)';mctx.fillRect(110,50,10,20)
   const maskedRaw=psd.writePsd({width:320,height:180,canvas:maskedComposite,children:[{name:'masked',left:100,top:50,canvas:make(40,20,'red'),mask:{left:100,top:50,defaultColor:0,canvas:mask}},{name:'background',canvas:make(320,180,'blue')}]})
   const maskedArt=await motion.readWebPsd(maskedRaw),maskedLayer=maskedArt.layers.find(l=>l.name==='masked'),maskedPixels=maskedLayer.canvas.getContext('2d')
   if(maskedPixels.getImageData(5,5,1,1).data[3]!==255||maskedPixels.getImageData(15,5,1,1).data[3]!==128||maskedPixels.getImageData(30,5,1,1).data[3]!==0)throw Error('Raster mask alpha or document coordinates incorrect')
   const maskVariant=async settings=>motion.readWebPsd(psd.writePsd({width:320,height:180,canvas:maskedComposite,children:[{name:'masked',left:100,top:50,canvas:make(40,20,'red'),mask:{left:100,top:50,defaultColor:0,canvas:mask,...settings}},{name:'background',canvas:make(320,180,'blue')}]}))
   const relative=await maskVariant({left:0,top:0,positionRelativeToLayer:true,userMaskDensity:.5}),relativeAlpha=relative.layers.find(l=>l.name==='masked').canvas.getContext('2d')
   if(Math.abs(relativeAlpha.getImageData(15,5,1,1).data[3]-192)>1||Math.abs(relativeAlpha.getImageData(30,5,1,1).data[3]-128)>1)throw Error('Relative raster mask or density incorrect')
   const disabledMask=await maskVariant({disabled:true});if(disabledMask.layers.find(l=>l.name==='masked').canvas.getContext('2d').getImageData(30,5,1,1).data[3]!==255)throw Error('Disabled mask applied')
   const whiteOutside=await maskVariant({defaultColor:255});if(whiteOutside.layers.find(l=>l.name==='masked').canvas.getContext('2d').getImageData(30,5,1,1).data[3]!==255)throw Error('White mask background ignored')
   let featherRejected=false;try{await maskVariant({userMaskFeather:2})}catch{featherRejected=true}if(!featherRejected)throw Error('Unsupported feather silently accepted')
   const composite=make(320,180,'#0000ff');composite.getContext('2d').drawImage(make(60,80,'#ff0000'),100,50)
   const raw=psd.writePsd({width:320,height:180,canvas:composite,children:[{name:'subject',left:100,top:50,canvas:make(60,80,'#ff0000')},{name:'background',canvas:make(320,180,'#0000ff')}]})
   const art=await motion.readWebPsd(raw),keys=[{t:0,x:.5,y:.5,scale:1,rotation:0,opacity:100},{t:1,x:.5,y:.5,scale:1,rotation:0,opacity:100}],scene={source:'psd',fit:'contain',direction:'',keys,effects:[],transition:'cut',layers:{'0':{depth:0,keys:[keys[0],{...keys[1],x:.55}]}}}
   const c=make(320,180,'black');motion.drawWebMotion(c,art,scene,0);const initial=[...c.getContext('2d').getImageData(105,60,1,1).data]
   const maskMotion=make(320,180,'black');motion.drawWebMotion(maskMotion,maskedArt,scene,0);if(maskMotion.getContext('2d').getImageData(105,55,1,1).data[0]!==255)throw Error('Masked subject missing')
   motion.drawWebMotion(maskMotion,maskedArt,scene,1);if(maskMotion.getContext('2d').getImageData(105,55,1,1).data[2]!==255)throw Error('Mask did not move with subject')
   motion.drawWebMotion(c,art,scene,1);const moved=[...c.getContext('2d').getImageData(105,60,1,1).data]
   const audio=new AudioBuffer({length:48000,numberOfChannels:1,sampleRate:48000});for(let i=0;i<48000;i++)audio.getChannelData(0)[i]=Math.sin(i/48000*440*Math.PI*2)*.1
   const shot={number:1,start:0,end:1,artwork:art,motion:scene};let progress=0
   const blob=await motion.exportWebMotion([shot],audio,[{start:.2,end:.8,text:'웹 제작 검증'}],'16:9',24,new AbortController().signal,n=>progress=n)
   const base64=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(blob)})
   let rejected=false;const cancel=new AbortController();cancel.abort();try{await motion.exportWebMotion([shot],audio,[],'16:9',24,cancel.signal,()=>{})}catch{rejected=true}
   let invalidRejected=false;try{await motion.readWebPsd(psd.writePsd({width:320,height:180,canvas:make(320,180,'green'),children:[{canvas:make(320,180,'red')}]}))}catch{invalidRejected=true}
   if(!invalidRejected)throw Error('Mismatched PSD composite was accepted')
   const mix=await motion.mixWebMotionAudio(audio,[{buffer:audio,start:.5,end:1,volume:.5,loop:false,fadeIn:0,fadeOut:0}]);if(Math.abs(mix.getChannelData(0)[1000]-audio.getChannelData(0)[1000])>.001||Math.abs(mix.getChannelData(0)[30011]-audio.getChannelData(0)[30011]*1.5)>.001)throw Error('Audio mix changed timing')
   window.testPsd=raw
   const vertical=await motion.exportWebMotion([shot],audio,[],'9:16',24,new AbortController().signal,()=>{})
   const order=[],lazy=[0,1].map(i=>({number:i+1,start:i*.5,end:(i+1)*.5,artwork:{width:0,height:0,layers:[]},motion:scene,load:async()=>{order.push('load'+i);return {artwork:art}},dispose:()=>order.push('release'+i)}))
   const lazyOutput=await motion.exportWebMotion(lazy,audio,[],'16:9',24,new AbortController().signal,()=>{})
   if(order.join(',')!=='load0,release0,load1,release1')throw Error('Source frames were not released between scenes')
   await motion.releaseWebMotionFile(lazyOutput);await motion.releaseWebMotionFile(vertical);await motion.releaseWebMotionFile(blob)
   return {initial,moved,layers:art.layers.map(l=>l.name),bytes:blob.size,verticalBytes:vertical.size,progress,base64,rejected,invalidRejected,lazy:order}
  })
  assert.deepEqual(evidence.layers,['background','subject']);assert.deepEqual(evidence.initial,[255,0,0,255]);assert.deepEqual(evidence.moved,[0,0,255,255]);assert.equal(evidence.progress,100);assert.ok(evidence.bytes>1000);assert.equal(evidence.rejected,true)
  const output=path.resolve(root,'../output/web-motion-browser-test');fs.mkdirSync(output,{recursive:true});fs.writeFileSync(path.join(output,'final.mp4'),Buffer.from(evidence.base64,'base64'));delete evidence.base64
  fs.writeFileSync(path.join(output,'evidence.json'),JSON.stringify(evidence,null,2));assert.deepEqual(errors,[])
  let saved=false,reviewed=false,providerCalls=0
  const wav=Buffer.alloc(44+96000);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(48000,24);wav.writeUInt32LE(96000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(96000,40)
  for(let i=0;i<48000;i++)wav.writeInt16LE(Math.round(Math.sin(i/48000*440*Math.PI*2)*3200),44+i*2)
  await page.route('**/api/std/projects/fixture/**',async route=>{const request=route.request(),url=new URL(request.url()),body=request.method()==='POST'?request.postDataJSON():{}
   if(url.pathname.endsWith('/web-motion')){
    if(request.method()==='GET')return route.fulfill({json:{scenes:[{number:1,title:'테스트',start:0,end:1,source:{id:'psd',kind:'psd',url:'/test.psd'}}],audio:{id:'audio',url:'/voice.wav'},audio_error:'',subtitles:[{start:0,end:1,text:'웹 영상'}],ai_jobs:[]}})
    if(body.action==='review'){reviewed=true;return route.fulfill({json:{render_queue_id:'final'}})}providerCalls++;return route.fulfill({json:{error:'Unexpected provider call'},status:500})
   }
   if(url.pathname.endsWith('/assets/init'))return route.fulfill({json:{...body,storage_provider:'gcs',storage_path:'final.mp4',storage_bucket:'bucket',storage_upload_url:'http://localhost:43199/upload'}})
   if(url.pathname.endsWith('/assets/complete')){saved=true;return route.fulfill({json:{asset:{id:'final'}}})}
   return route.fulfill({json:{}})
  })
  const psdBuffer=Buffer.from(await page.evaluate(()=>Array.from(new Uint8Array(window.testPsd))))
  await page.route('**/test.psd',r=>r.fulfill({contentType:'image/vnd.adobe.photoshop',body:psdBuffer}));await page.route('**/voice.wav',r=>r.fulfill({contentType:'audio/wav',body:wav}));await page.route('**/upload',r=>r.fulfill({status:200,body:''}))
  const cssDir=path.join(root,'.next/static/css');if(fs.existsSync(cssDir))for(const file of fs.readdirSync(cssDir).filter(f=>f.endsWith('.css')))await page.addStyleTag({path:path.join(cssDir,file)})
  await page.evaluate(()=>{function Fixture(){const [draft,setDraft]=React.useState({version:1,enabled:false,aspect:'16:9',fps:24,scenes:{}});return React.createElement(window.Editor,{draft,onChange:setDraft,onSave:async d=>{window.savedDraft=d;setDraft(d)},projectId:'fixture',headers:{},disabled:false})};ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(Fixture))})
  await page.getByRole('button',{name:'카메라 접근',exact:true}).click()
  await page.getByRole('button',{name:'AE 없이 전체 최종 MP4 제작',exact:true}).click()
  await page.getByRole('link',{name:'최종 MP4 다운로드'}).waitFor({timeout:60000})
  await page.getByRole('button',{name:'최종 영상 웹 저장',exact:true}).click();await page.getByRole('button',{name:'영상 확인 완료 · 관리자 검수 요청'}).click()
  await page.getByText('관리자 검수 목록에 전달했습니다.',{exact:false}).waitFor();assert.ok(saved&&reviewed);assert.equal(providerCalls,0)
  await page.screenshot({path:path.join(output,'web-studio.png'),fullPage:true});assert.deepEqual(errors,[])
  console.log('PASS browser UI: stored PSD + finalized recording → full MP4 → signed upload → admin review; no paid provider calls')
  await page.evaluate(()=>{const div=document.createElement('div');div.id='production-choice';document.body.append(div);function Choice(){const [draft,setDraft]=React.useState({version:1,enabled:true,aspect:'16:9',fps:24,scenes:{'1':window.motionSettings.motionPreset('impact')}});window.selectionDraft=draft;return React.createElement(window.Production,{aePreparation:React.createElement('div',{'data-testid':'legacy-ae-preparation'},'기존 AE 장면 연출'),value:draft,scenes:[{scene_number:1}],projectId:'fixture',headers:{},disabled:false,onSave:async value=>setDraft(value),onUpload:async()=>{}})};ReactDOM.createRoot(div).render(React.createElement(Choice))})
  await page.getByRole('radio',{name:'기존 AE 방식 · 기본',exact:false}).check();assert.equal(await page.getByRole('radio',{name:'기존 AE 방식 · 기본',exact:false}).isChecked(),true)
  assert.equal(await page.locator('#production-choice [aria-label="웹 모션 제작"]').count(),0);assert.equal(await page.getByTestId('legacy-ae-preparation').count(),1)
  await page.getByRole('radio',{name:'Motion Studio · 추가 옵션',exact:false}).check();assert.equal(await page.evaluate(()=>window.selectionDraft.production_method),'motion_studio')
  await page.locator('#production-choice [aria-label="웹 모션 제작"]').waitFor();assert.equal(await page.getByTestId('legacy-ae-preparation').count(),0)
  await page.getByRole('radio',{name:'기존 AE 방식 · 기본',exact:false}).check();assert.equal(await page.evaluate(()=>window.selectionDraft.scenes[1].effects[0].type),'impact_shake')
  assert.equal(await page.locator('#production-choice [aria-label="웹 모션 제작"]').count(),0);assert.equal(await page.getByTestId('legacy-ae-preparation').count(),1)
  console.log('PASS production method selection: AE default, explicit optional studio, original AE settings restored')
  const realPsd=path.resolve(root,'../output/ae-psd-wuxia-3285/wuxia-split-layered.psd')
  if(fs.existsSync(realPsd)){
   await page.route('**/real.psd',r=>r.fulfill({contentType:'image/vnd.adobe.photoshop',body:fs.readFileSync(realPsd)}))
   const real=await page.evaluate(async()=>{const raw=await (await fetch('/real.psd')).arrayBuffer(),art=await window.motion.readWebPsd(raw),c=document.createElement('canvas');c.width=960;c.height=540;document.body.replaceChildren(c)
    const keys=[{t:0,x:.5,y:.5,scale:1,rotation:0,opacity:100},{t:1,x:.5,y:.5,scale:1.06,rotation:0,opacity:100}]
    window.motion.drawWebMotion(c,art,{source:'psd',fit:'contain',direction:'',keys,effects:[{type:'light_sweep',start:0,end:1,intensity:.3,center:[.5,.5],radius:.5,color:[1,.8,.4]}],transition:'cut'},.5)
    return {width:art.width,height:art.height,layers:art.layers.map(l=>l.name)}
   });assert.equal(real.layers.length,3);await page.screenshot({path:path.join(output,'real-psd-preview.png')});console.log('PASS existing layered PSD in browser: '+JSON.stringify(real))
  }
  console.log('PASS actual browser: PSD stacking and independent layer motion, 1080p H264/AAC final MP4 with captions, cancellation; '+JSON.stringify(evidence))
 }finally{await browser.close()}
}
main().catch(e=>{console.error(e);process.exitCode=1})
