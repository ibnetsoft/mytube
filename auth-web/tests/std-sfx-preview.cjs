const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict'),test=require('node:test');
const {setImmediate:tick}=require('node:timers/promises');
test('SFX shares narration context, authenticates GCS loading, seeks once, and stops at pause or cue end',async()=>{
 let cursor=0,effects=[],cells=[],deps=[],props,fetches=[],starts=[],stops=0;
 const hooks={useRef:v=>{const i=cursor++;return cells[i]||(cells[i]={current:v})},useState:v=>{const i=cursor++;if(!(i in cells))cells[i]=v;return[cells[i],v=>{cells[i]=v}]},useMemo:(f,d)=>{const i=cursor++;if(!deps[i]||d.some((x,j)=>x!==deps[i][j])){cells[i]=f();deps[i]=d}return cells[i]},useEffect:(f,d)=>{const i=cursor++;if(!deps[i]||!d||d.some((x,j)=>x!==deps[i][j])){const cleanup=cells[i];effects.push(()=>{cleanup?.();cells[i]=f()});deps[i]=d}}};
 const context={currentTime:0,state:'running',destination:{},createBufferSource:()=>({connect(){return this},disconnect(){},start(...a){starts.push(a)},stop(){stops++}}),createGain:()=>({gain:{value:0},connect(){return this},disconnect(){}})};
 const buffer={duration:3,sampleRate:10,numberOfChannels:1,getChannelData:()=>new Float32Array(30).fill(.5)};
 const code=ts.transpileModule(fs.readFileSync(require.resolve('../components/SubtitleSfxPreview.tsx'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText+'\nexports.Track=SfxTrack;';
 const e={};new Function('exports','require','fetch','OfflineAudioContext','AudioContext',code)(e,n=>n==='react'?hooks:n==='react/jsx-runtime'?{jsx:()=>null,jsxs:()=>null}:n.includes('stdSfxCues')?{resolveSfxCues:()=>[]}: {audioWaveformPeaks:()=>[.5]},async(u,o)=>{fetches.push({u,o});return{ok:true,arrayBuffer:async()=>new ArrayBuffer(1)}},class{async decodeAudioData(){return buffer}},class{constructor(){throw Error('Must reuse narration context')}});
 props={cue:{id:'cue',asset_id:'asset',start:100,duration:2,volume_db:-18,subtitle_index:0},asset:{id:'asset'},projectId:'project',headers:{Authorization:'Bearer fixture'},time:100.2,playing:true,onError:()=>{},audioContextRef:{current:context},subtitles:[{start_num:100,end_num:104}]};
 function render(p={}){props={...props,...p};cursor=0;e.Track(props);const q=effects;effects=[];q.forEach(f=>f())}
 render();await tick();await tick();render();
 assert.equal(fetches.length,1);assert.equal(fetches[0].o.headers.Authorization,'Bearer fixture');assert.ok(fetches[0].u.includes('assets/file?assetId=asset'));
 assert.equal(starts.length,1);assert.ok(Math.abs(starts[0][1]-.2)<1e-6);assert.ok(Math.abs(starts[0][2]-1.8)<1e-6);
 context.currentTime=.2;render({time:100.4});assert.equal(starts.length,1,'clock ticks never restart audio');
 render({time:101.5});assert.equal(starts.length,2,'seek restarts at the requested offset');
 render({playing:false});assert.equal(stops,2);
 render({playing:true,time:102.1});assert.equal(starts.length,2,'nothing plays beyond saved duration');
});
