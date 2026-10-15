const fs=require('node:fs'),ts=require('typescript'),assert=require('node:assert/strict'),test=require('node:test');
const {setImmediate:tick}=require('node:timers/promises');const load=require('./load-ts.cjs');
const helper=load('auth-web/lib/stdSfxCues.ts');
function nodes(n){if(!n||typeof n!=='object')return [];if(Array.isArray(n))return n.flatMap(nodes);return [n,...nodes(n.props?.children)]}
test('editor inserts at the selected boundary and removes through the edit dialog',async()=>{
 let cursor=0,cells=[],saved;
 const hooks={useState:v=>{const i=cursor++;if(!(i in cells))cells[i]=v;return[cells[i],v=>{cells[i]=v}]},useEffect:()=>{}};
 const e={};const code=ts.transpileModule(fs.readFileSync('auth-web/components/SubtitleSfxEditor.tsx','utf8'),{compilerOptions:{module:1,target:7,jsx:4}}).outputText;
 new Function('exports','require',code)(e,id=>id==='react'?hooks:id==='react/jsx-runtime'?{jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'fragment'}:id.includes('stdUiText')?{stdUiText:(_locale,text)=>text}:id.includes('stdThumbnailUrl')?{persistentThumbnailUrl:()=>''}:helper);
 const sub={id:'sub',text:'문을 열고 들어왔다',scene_number:3,start_num:10,end_num:16};
 let props={subtitle:sub,subtitleIndex:0,subtitles:[sub],assets:[{id:'sound',file_name:'door.mp3'}],cues:[],selectedAssetId:'sound',onSelect:()=>{},onSave:async cues=>{saved=cues},onEdit:()=>{},onError:msg=>{throw Error(msg)}};
 const render=()=>{cursor=0;return e.default(props)};
 nodes(render()).find(n=>n.props?.['aria-label']==='1번째 단어 뒤 효과음 삽입').props.onClick();await tick();
 assert.equal(saved[0].start,12);assert.equal(saved[0].word_boundary,1);assert.equal(sub.text,'문을 열고 들어왔다');
 props={...props,cues:[...saved,{...saved[0],id:'other',word_boundary:2}]};
 nodes(render()).find(n=>n.props?.['aria-label']==='door.mp3 효과음 편집').props.onClick();
 await nodes(render()).find(n=>n.props?.children==='효과음 제거').props.onClick();
 assert.equal(saved.find(c=>c.id===props.cues[0].id).enabled,false);
 assert.equal(saved.find(c=>c.id==='other').enabled,true);
});
