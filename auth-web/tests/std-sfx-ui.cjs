const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
const helper={};new Function('exports',ts.transpile(fs.readFileSync('auth-web/lib/stdSfxCues.ts','utf8'),{module:1,target:7}))(helper);
function load(file,react,extra=''){const out={};new Function('exports','require',ts.transpile(fs.readFileSync(file,'utf8')+extra,{module:1,target:7,jsx:4})) (out,id=>id==='react'?react:id==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'fragment'}:helper);return out;}
function nodes(n){if(!n||typeof n!=='object')return [];if(Array.isArray(n))return n.flatMap(nodes);return [n,...nodes(n.props?.children)]}
(async()=>{
let saved;const Editor=load('auth-web/components/SubtitleSfxEditor.tsx',{useState:()=>[false,()=>{}],Fragment:'fragment'}).default;
const sub={id:'sub',text:'문을 열고 들어왔다',start_num:10,end_num:16};
const props={subtitle:sub,subtitleIndex:0,subtitles:[sub],assets:[{id:'sound',file_name:'door.mp3'}],cues:[],selectedAssetId:'sound',onSelect:()=>{},onSave:async cues=>{saved=cues},onEdit:()=>{},activeTokenIndex:-1,onError:msg=>{throw Error(msg)}};
let tree=Editor(props);let insert=nodes(tree).find(n=>n.props?.['aria-label']==='1번째 단어 뒤 효과음 삽입');insert.props.onClick();await Promise.resolve();assert.equal(saved.length,1);assert.equal(saved[0].start,12);assert.equal(saved[0].word_boundary,1);assert.equal(sub.text,'문을 열고 들어왔다');
tree=Editor({...props,cues:[...saved,{...saved[0],id:'other',word_boundary:2}]});nodes(tree).find(n=>n.props?.['aria-label']==='door.mp3 효과음 삭제').props.onClick();await Promise.resolve();assert.equal(saved.length,1);assert.equal(saved[0].id,'other');
function sync(time,playing){let effects=[],plays=0,pauses=0;const audio={currentTime:0,duration:2,readyState:1,paused:true,play:async()=>{plays++},pause:()=>pauses++,addEventListener(){},removeEventListener(){}};const Track=load('auth-web/components/SubtitleSfxPreview.tsx',{useState:()=>['test.mp3',()=>{}],useRef:()=>({current:audio}),useEffect:f=>effects.push(f)},'\nexport { SfxTrack };').SfxTrack;Track({cue:{start:12,volume_db:-18},asset:{id:'s',metadata:{storage_public_url:'test.mp3'}},projectId:'p',headers:{},time,playing,onError:()=>{}});effects[1]();return {audio,plays,pauses}}
assert.equal(sync(11,true).plays,0);let playing=sync(13,true);assert.equal(playing.plays,1);assert.equal(playing.audio.currentTime,1);assert.equal(sync(13,false).pauses,1);assert.equal(sync(15,true).plays,0);
console.log('PASS: editor insert/delete callbacks and preview timing, seek, pause, end-of-file without repeat');
})().catch(e=>{console.error(e);process.exit(1)});
