const fs=require('fs'),http=require('http'),assert=require('node:assert/strict'),ts=require('../node_modules/typescript');
const {chromium}=require('../node_modules/@playwright/test');
(async()=>{
 const react=fs.readFileSync(require.resolve('react').replace(/index\.js$/,'umd/react.production.min.js'),'utf8');
 const dom=fs.readFileSync(require.resolve('react-dom').replace(/index\.js$/,'umd/react-dom.production.min.js'),'utf8');
 const component=ts.transpile(fs.readFileSync('components/StdAeMouthPanel.tsx','utf8'),{module:1,target:7,jsx:2});
 const html=`<div id="root"></div><script>${react}</script><script>${dom}</script><script>
 const exports={};new Function('exports','require',${JSON.stringify(component)})(exports,()=>React);
 window.requests=[];let status='direction_pending',rowStatus='direction_pending';
 window.fetch=async(url,options={})=>{if(options.method==='POST'){
  const body=JSON.parse(options.body);window.requests.push(body);
  if(body.action==='approve_direction'){status='review_pending';rowStatus='review_pending';}
  if(body.action==='review'){status='reviewed';rowStatus='approved';}
  return {ok:true,json:async()=>({success:true})};}
  return {ok:true,json:async()=>({applicable:true,fingerprint:'current-tts-image',status,results:[{number:19,status:rowStatus,speakers:['소녀'],direction:'소녀의 입만 대사 구간에서 움직입니다.',videoUrl:''},{number:20,status:'skipped',speakers:[],reason:'내레이션'}]})};};
 ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(exports.default,{projectId:'p',headers:{}}));
 </script>`;
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html;charset=utf-8');res.end(html)});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage();await page.goto('http://127.0.0.1:'+server.address().port);
  await page.getByText('소녀의 입만 대사 구간에서 움직입니다.',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'입모양·AE 결과 승인',exact:true}).count(),0);
  await page.getByRole('button',{name:'표시된 지침 승인 · AE 작업 시작',exact:true}).click();
  await page.getByRole('button',{name:'입모양·AE 결과 승인',exact:true}).click();
  await page.getByText('검수가 완료되었습니다. 제출 버튼으로 최종 렌더링을 진행할 수 있습니다.',{exact:true}).waitFor();
  const calls=await page.evaluate(()=>window.requests);
  assert.deepEqual(calls.map(r=>r.action),['approve_direction','review']);assert.equal(calls[1].number,19);
  assert.ok(calls.every(r=>r.fingerprint==='current-tts-image'));
  console.log('PASS: scene directions precede AE approval, then rendered output requires a separate review');
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
