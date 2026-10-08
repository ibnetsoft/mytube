const fs=require('fs'),ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server'),assert=require('node:assert/strict'),path=require('node:path');
process.chdir(path.resolve(__dirname,'..'));
function load(file,requireFn){const exports={};new Function('exports','require',ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:1,target:9,jsx:4}}).outputText)(exports,requireFn||require);return exports}
const copy=load('lib/stdRegionMotionCopy.ts'),motion=load('lib/stdRegionMotion.ts');
const scene={number:13,imageId:'img',duration:5,subtitles:[{id:'s',text:'hello',start:0,end:5}]};
const region={id:'r',name:'Tree',action:'horizontal',polygon:[[.1,.1],[.2,.1],[.2,.2]],anchor:[.1,.1],amplitude:2,period:2,cycles:1,start:0,subtitleId:'s'};
let i=0;const states={0:true,1:[scene],2:13,3:[region],6:'data:image/png;base64,',7:'hash'};
const component=load('components/StdRegionMotionEditor.tsx',name=>{
 if(name==='react')return {...React,useState:initial=>[Object.hasOwn(states,i)?states[i++]: (i++,initial),()=>{}],useEffect:()=>{},useRef:v=>({current:v})};
 if(name==='react-dom')return {createPortal:n=>n};
 if(name.includes('StdRegionLayers'))return {default:()=>null};
 if(name.includes('stdRegionMotionCopy'))return copy;
 if(name.includes('stdRegionMotion'))return motion;
 return require(name);
});
global.document={body:{}};
const html=renderToStaticMarkup(React.createElement(component.default,{projectId:'p',headers:{},locale:'th'}));
assert.match(html,/กำหนดการเคลื่อนไหวของส่วนภาพ/);assert.match(html,/เลื่อนซ้ายขวาซ้ำ/);assert.match(html,/ขอสร้างวิดีโอ AIR STUDIO/);assert.doesNotMatch(html,/[가-힣]/);
assert.equal(motion.parseRegionMotionCommand('เลื่อนซ้ายขวา 3% ทุก 2 วินาที 3 ครั้ง').cycles,3);
console.log('PASS: full Thai popup, motion names, buttons and Thai command');
