const assert=require('node:assert/strict'),fs=require('fs'),ts=require('typescript'),path=require('path');
function load(name){const e={};const file=path.join(__dirname,'../lib',name+'.ts');new Function('exports','require',ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText)(e,n=>load(n.replace('./','')));return e;}
const {thumbnailEditorBackground,thumbnailLines,drawThumbnail,editableThumbnailError}=load('stdThumbnailRender');
const design={contract:'editable-background-v1',editor_bg_url:'https://x/raw.png',text_layers:[],render_status:'awaiting_user_save'};
assert.ok(editableThumbnailError(design,'https://x/raw.png',true));
assert.equal(editableThumbnailError(design,null,false),'');
assert.equal(editableThumbnailError({...design,render_status:'completed',thumbnail_url:'https://x/final.png'},'https://x/final.png',true),'');
assert.equal(thumbnailEditorBackground({thumbnail_url:'https://x/final.png',thumbnail_design:{thumbnail_url:'https://x/final.png'}}),'');
assert.equal(thumbnailEditorBackground({thumbnail_url:'https://x/final.png',thumbnail_design:{editor_bg_url:'https://x/final.png'}}),'');
assert.equal(editableThumbnailError({contract:'editable-background-v1',render_status:'awaiting_background',text_layers:[]},null,false),'');
assert.equal(thumbnailEditorBackground({thumbnail_design:{editor_bg_url:'blob:bad'},thumbnail_bg_url:'https://x/bg.png'}),'https://x/bg.png');
assert.equal(thumbnailEditorBackground({thumbnail_design:{editor_bg_url:'https://x/raw.png',thumbnail_url:'https://x/final.png'}}),'https://x/raw.png');
assert.deepEqual(thumbnailLines({measureText:t=>({width:t.length*10})},'가나다라\n마바',20),['가나','다라','마바']);
(async()=>{
 let fontsReady=false;const calls=[];
 global.document={fonts:{load:async()=>{fontsReady=true},ready:Promise.resolve()}};
 const ctx={drawImage:()=>assert.ok(fontsReady),save(){},restore(){},scale:(...args)=>calls.push(['scale',...args]),
 measureText:t=>({width:t.length*10}),strokeText:(...args)=>calls.push(['stroke',...args]),fillText:(...args)=>calls.push(['fill',...args])};
 const canvas={getContext:()=>ctx};
 const layer={id:'one',text:'대사',fontFamily:'sans-serif',fontSize:34,strokeWidth:0,x:0,y:0};
 await drawThumbnail(canvas,{naturalWidth:1920,naturalHeight:1080},[layer]);
 assert.equal(canvas.width,1280);assert.equal(canvas.height,720);
 assert.deepEqual(calls.find(c=>c[0]==='fill'),['fill','대사',0,0]);
 assert.ok(!calls.some(c=>c[0]==='stroke'));
 assert.deepEqual(calls.find(c=>c[0]==='scale'),['scale',1280/480,1280/480]);
 const page=fs.readFileSync(path.join(__dirname,'../app/std/page.tsx'),'utf8');
 assert.ok(page.includes('renderThumbnailFile(')&&page.includes('<StdThumbnailPreview'));
 assert.ok(!page.includes('setThumbBgUrl(persistedThumbnailUrl)'));
 assert.ok(!page.includes('1번 씬 이미지를 대신 표시'));
 console.log('thumbnail renderer/background separation tests passed');
})().catch(e=>{console.error(e);process.exitCode=1});
