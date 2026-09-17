const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
const jsx={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
const catalog={};new Function('exports',ts.transpile(fs.readFileSync('auth-web/lib/voiceStudioCatalog.ts','utf8'),{module:1,target:7}))(catalog);
const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
let calls=0;global.fetch=async()=>{calls++;return {ok:true,blob:async()=>new Blob(['sample'])}};
global.document={body:{},activeElement:{focus(){}},addEventListener(){},removeEventListener(){}};
function harness(initialTab){let state=[],refs=[],index=0,ri=0,effects=[],applied=[],closed=0;
 const react={useState:init=>{const i=index++;if(!(i in state))state[i]=init;return [state[i],v=>state[i]=v]},useRef:init=>{const i=ri++;return refs[i]??=( {current:init})},useEffect:fn=>{if(!effects.length)effects.push(fn)}};
 const exports={};new Function('exports','require',ts.transpile(fs.readFileSync('auth-web/components/UnifiedVoiceDialog.tsx','utf8'),{module:1,target:7,jsx:4}))(exports,id=>id==='react'?react:id==='react-dom'?{createPortal:x=>x}:id==='react/jsx-runtime'?jsx:catalog);
 const props={value:'gemini:Charon',initialTab,title:'One subtitle',headers:{},voices:[{id:'eleven-1',name:'George',gender:'male',preview_url:'sample.mp3'},{id:'google_ko',name:'Google Korean',category:'google'}],onApply:(...args)=>applied.push(args),onClose:()=>closed++};
 const render=()=>{index=ri=0;return nodes(exports.default(props))};return {render,effects,refs,applied,get closed(){return closed}};
}
(async()=>{
 for(const tab of ['google','elevenlabs']){const h=harness(tab);let tree=h.render();assert.equal(tree.filter(n=>n.props?.role==='dialog').length,1);assert.equal(tree.find(n=>n.props?.role==='tab'&&n.props['aria-selected']).props.children,tab==='google'?'Google 성우':'ElevenLabs 성우');assert.equal(calls,0);
 tree.find(n=>n.props?.role==='tab'&&n.props.children==='ElevenLabs 성우').props.onClick();tree=h.render();assert.equal(calls,0);assert(tree.some(n=>n.props?.children==='George'));assert(!tree.some(n=>n.type==='p'&&n.props?.children==='Charon'));
 tree.find(n=>n.type==='button'&&n.props.children==='선택').props.onClick();tree=h.render();assert.deepEqual(h.applied,[]);await tree.find(n=>n.type==='button'&&n.props.children==='선택 완료').props.onClick();assert.equal(h.applied[0][0],'eleven-1');assert.equal(h.closed,1);
 }
 const h=harness('google');let tree=h.render();tree.find(n=>n.type==='button'&&n.props.children==='취소').props.onClick();assert.deepEqual(h.applied,[]);
 // Unmount stops the player and aborts pending sample work.
 let stopped=0;h.refs[0].current={pause:()=>stopped++};const cleanup=h.effects[0]();h.refs[2].current=new AbortController();cleanup();assert.equal(stopped,1);assert(h.refs[2].current.signal.aborted);
 // Google samples are requested explicitly, never on mount or tab switches.
 const g=harness('google');let plays=0;g.refs;tree=g.render();g.refs[0].current={pause(){},play:async()=>plays++};await tree.find(n=>n.type==='button'&&n.props.children==='▶ 미리듣기'&&!n.props.disabled).props.onClick();await new Promise(r=>setTimeout(r,0));assert.equal(calls,1);assert.equal(plays,1);
 console.log('PASS: initial provider tabs, single dialog, no automatic API calls, selection/cancel, preview cleanup and explicit sample');
})().catch(e=>{console.error(e);process.exitCode=1});
