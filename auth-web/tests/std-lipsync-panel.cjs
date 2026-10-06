const fs=require('fs'),http=require('http'),path=require('path'),assert=require('node:assert/strict'),ts=require('../node_modules/typescript');
const {chromium}=require('../node_modules/@playwright/test');
(async()=>{
 const react=fs.readFileSync(require.resolve('react').replace(/index\.js$/,'umd/react.production.min.js'),'utf8');
 const dom=fs.readFileSync(require.resolve('react-dom').replace(/index\.js$/,'umd/react-dom.production.min.js'),'utf8');
 const component=ts.transpile(fs.readFileSync('components/StdLipSyncPanel.tsx','utf8'),{module:1,target:7,jsx:2});
 const image='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#456"/></svg>');
 const html=`<div id="root" style="width:400px"></div><script>${react}</script><script>${dom}</script><script>
 const exports={};new Function('exports','require',${JSON.stringify(component)})(exports,()=>React);
 window.requests=[];window.saves=0;
 let status='not_started';
 window.fetch=async(url,options={})=>{if(options.method==='POST'){window.requests.push(JSON.parse(options.body));status='queued';return {ok:true,json:async()=>({success:true})};}
 return {ok:true,json:async()=>({configured:true,scenes:[{number:7,fingerprint:'confirmed-audio-image',speakers:['소녀','어머니'],imageUrl:${JSON.stringify(image)},status,points:{}}]})};};
 ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(exports.default,{projectId:'project',headers:{},beforeSave:async()=>{window.saves++;}}));
 </script>`;
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html;charset=utf-8');res.end(html);});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);
  await page.getByRole('button',{name:'대사 영상 · 립싱크',exact:true}).click();
  const img=page.getByAltText('씬 7: 말할 인물의 얼굴을 클릭하세요');await img.waitFor();
  const box=await img.boundingBox();await img.click({position:{x:box.width*.3,y:box.height*.4}});
  await page.getByRole('combobox').selectOption('어머니');await img.click({position:{x:box.width*.7,y:box.height*.4}});
  await page.getByRole('button',{name:'대사 영상 생성',exact:true}).click();
  await page.waitForFunction(()=>window.requests.length===1);
  const result=await page.evaluate(()=>({requests:window.requests,saves:window.saves}));
  assert.equal(result.saves,1);assert.equal(result.requests[0].scene_number,7);
  assert.equal(result.requests[0].fingerprint,'confirmed-audio-image');
  assert.ok(Math.abs(result.requests[0].points['소녀'][0]-.3)<.01);
  assert.ok(Math.abs(result.requests[0].points['어머니'][0]-.7)<.01);
  console.log('PASS: saved subtitles, confirmed input fingerprint and separate speaker faces reach the generation request');
 } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
