const fs=require('fs'),path=require('path');
const ROOT=path.resolve(__dirname,'../../../../');
const modules=[path.join(ROOT,'output/wuxia-series-rebuild/episode-01/packaging/tooling/node_modules'),path.join(ROOT,'auth-web/node_modules')];
const ts=require(require.resolve('typescript',{paths:modules}));
require.extensions['.ts']=(m,f)=>m._compile(ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,f);
const mode=process.argv[2];
if(mode==='ready'){
 const {isPreparedUserTopic,hasReadySceneMediaPrompts}=require(path.join(ROOT,'auth-web/lib/preparedTopic.ts'));
 const row=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
 console.log(JSON.stringify({ready:isPreparedUserTopic(row),prompts_ready:hasReadySceneMediaPrompts(row)}));
}else if(mode==='thumbnail'){
 (async()=>{
 const pkg=modules[0];
 const {createCanvas,loadImage,GlobalFonts}=require(require.resolve('@napi-rs/canvas',{paths:[pkg]}));
 GlobalFonts.registerFromPath(path.join(__dirname,'../fonts/NotoSansKR-Bold.ttf'),'Noto Sans KR');
 GlobalFonts.registerFromPath(path.join(__dirname,'../fonts/BlackHanSans-Regular.ttf'),'Black Han Sans');
 global.document={fonts:{load:async()=>[],ready:Promise.resolve()}};
 const {drawThumbnail}=require(path.join(ROOT,'auth-web/lib/stdThumbnailRender.ts'));
 const design=JSON.parse(fs.readFileSync(path.join(__dirname,'thumbnail-design.json'),'utf8'));
 const image=await loadImage(path.join(__dirname,'thumbnail-bg-v1.png'));
 if(!image.naturalWidth)Object.defineProperties(image,{naturalWidth:{value:image.width},naturalHeight:{value:image.height}});
 const canvas=createCanvas(1280,720);await drawThumbnail(canvas,image,design.text_layers);
 fs.writeFileSync(path.join(__dirname,'thumbnail-final.png'),canvas.toBuffer('image/png'));
 console.log(JSON.stringify({width:canvas.width,height:canvas.height,renderer:'auth-web/lib/stdThumbnailRender.ts:drawThumbnail',layers:design.text_layers.length}));
 })().catch(e=>{console.error(e);process.exitCode=1});
}
