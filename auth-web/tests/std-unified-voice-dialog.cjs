const fs=require('fs'),ts=require('typescript'),assert=require('node:assert/strict');
const jsx={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
const catalog={};new Function('exports',ts.transpile(fs.readFileSync('auth-web/lib/voiceStudioCatalog.ts','utf8'),{module:1,target:7}))(catalog);
const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
let calls=0;global.fetch=async()=>{calls++;return {ok:true,blob:async()=>new Blob(['sample'])}};
global.document={body:{},activeElement:{focus(){}},addEventListener(){},removeEventListener(){}};
const storage=new Map();global.localStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)};
function harness(initialTab,historyUserId,speakerContext){let state=[],refs=[],index=0,ri=0,effects=[],applied=[],closed=0;
 let firstRender=true;
 const react={useState:init=>{const i=index++;if(!(i in state))state[i]=init;return [state[i],v=>state[i]=v]},useRef:init=>{const i=ri++;return refs[i]??=( {current:init})},useEffect:fn=>{if(firstRender)effects.push(fn)}};
 const exports={};new Function('exports','require',ts.transpile(fs.readFileSync('auth-web/components/UnifiedVoiceDialog.tsx','utf8'),{module:1,target:7,jsx:4}))(exports,id=>id==='react'?react:id==='react-dom'?{createPortal:x=>x}:id==='react/jsx-runtime'?jsx:catalog);
 const props={speakerContext,historyUserId,value:'gemini:Charon',initialTab,title:'One subtitle',headers:{},voices:[{id:'eleven-1',name:'George',gender:'male',preview_url:'sample.mp3'},{id:'eleven-2',name:'Sarah',gender:'female',preview_url:'sample2.mp3'},{id:'google_ko',name:'Google Korean',category:'google'}],onApply:(...args)=>applied.push(args),onClose:()=>closed++};
 const render=()=>{index=ri=0;const result=nodes(exports.default(props));firstRender=false;return result};return {render,effects,refs,applied,get closed(){return closed}};
}
(async()=>{
 for(const tab of ['google','elevenlabs']){const h=harness(tab);let tree=h.render();assert.equal(tree.filter(n=>n.props?.role==='dialog').length,1);assert.equal(tree.find(n=>n.props?.role==='tab'&&n.props['aria-selected']).props.children,tab==='google'?'Google 성우':'ElevenLabs 성우');assert.equal(calls,0);
 tree.find(n=>n.props?.role==='tab'&&n.props.children==='ElevenLabs 성우').props.onClick();tree=h.render();assert.equal(calls,0);assert(tree.some(n=>n.props?.children==='George'));assert(!tree.some(n=>n.type==='p'&&n.props?.children==='Charon'));
 tree.find(n=>n.type==='button'&&n.props.children==='선택').props.onClick();tree=h.render();assert.deepEqual(h.applied,[]);await tree.find(n=>n.type==='button'&&n.props.children==='선택 완료').props.onClick();assert.equal(h.applied[0][0],'eleven-1');assert.equal(h.closed,1);
 }
 const h=harness('google');let tree=h.render();tree.find(n=>n.type==='button'&&n.props.children==='취소').props.onClick();assert.deepEqual(h.applied,[]);
 // Unmount stops the player and aborts pending sample work.
 let stopped=0;h.refs[0].current={pause:()=>stopped++};const cleanup=h.effects[1]();h.refs[2].current=new AbortController();cleanup();assert.equal(stopped,1);assert(h.refs[2].current.signal.aborted);
 // Google samples are requested explicitly, never on mount or tab switches.
 const g=harness('google');let plays=0;g.refs;tree=g.render();g.refs[0].current={pause(){},play:async()=>plays++};await tree.find(n=>n.type==='button'&&n.props.children==='▶ 미리듣기'&&!n.props.disabled).props.onClick();await new Promise(r=>setTimeout(r,0));assert.equal(calls,1);assert.equal(plays,1);
 // History records confirmed application only, survives reopening and is scoped per user.
 storage.set('air:recent-voices:v1:user-a',JSON.stringify(['eleven-2','eleven-1']));
 const history=harness('elevenlabs','user-a');history.render();history.effects[0]();
 let ordered=history.render();const names=tree=>tree.filter(n=>n.type==='p'&&n.props.title).map(n=>n.props.children);
 assert.deepEqual(names(ordered),['Sarah','George']);
 ordered.find(n=>n.type==='button'&&n.props.children==='선택').props.onClick();
 assert.deepEqual(JSON.parse(storage.get('air:recent-voices:v1:user-a')),['eleven-2','eleven-1']);
 ordered=history.render();await ordered.find(n=>n.type==='button'&&n.props.children==='선택 완료').props.onClick();
 assert.deepEqual(JSON.parse(storage.get('air:recent-voices:v1:user-a')),['eleven-2','eleven-1']);
 // Pick George (second card), then reopen: George must precede Sarah with no duplicate.
 ordered.filter(n=>n.type==='button'&&['선택','✓ 선택됨'].includes(n.props.children))[1].props.onClick();
 ordered=history.render();await ordered.find(n=>n.type==='button'&&n.props.children==='선택 완료').props.onClick();
 const reopened=harness('elevenlabs','user-a');reopened.render();reopened.effects[0]();assert.deepEqual(names(reopened.render()),['George','Sarah']);
 const other=harness('elevenlabs','user-b');other.render();other.effects[0]();assert.deepEqual(names(other.render()),['George','Sarah']);
 storage.set('air:recent-voices:v1:user-a','invalid json');const corrupt=harness('elevenlabs','user-a');corrupt.render();corrupt.effects[0]();assert.deepEqual(names(corrupt.render()),['George','Sarah']);
 const mismatch=harness('elevenlabs',undefined,{name:'덕수',gender:'male',count:2,thai:true});let mt=mismatch.render();
 mt.filter(n=>n.type==='button'&&['선택','✓ 선택됨'].includes(n.props.children))[1].props.onClick();mt=mismatch.render();
 assert.equal(mt.find(n=>n.type==='button'&&n.props.children==='선택 완료').props.disabled,true);
 assert(mt.some(n=>n.props?.role==='alert'));
 mt.filter(n=>n.type==='input'&&n.props.type==='checkbox')[1].props.onChange({target:{checked:true}});mt=mismatch.render();
 assert.equal(mt.find(n=>n.type==='button'&&n.props.children==='선택 완료').props.disabled,false);
 await mt.find(n=>n.type==='button'&&n.props.children==='선택 완료').props.onClick();assert.equal(mismatch.applied[0][2],true);
 const filters=harness('elevenlabs');let ft=filters.render();
 const cardNames=t=>t.filter(n=>n.type==='p'&&n.props.title).map(n=>n.props.children);
 ft.find(n=>n.type==='button'&&n.props.children==='여성').props.onClick();ft=filters.render();assert.deepEqual(cardNames(ft),['Sarah']);
 ft.find(n=>n.type==='button'&&n.props.children==='남성').props.onClick();ft=filters.render();assert.deepEqual(cardNames(ft),['George']);
 ft.find(n=>n.props?.role==='tab'&&n.props.children==='Google 성우').props.onClick();ft=filters.render();assert(cardNames(ft).includes('Charon'));assert(!cardNames(ft).includes('Achernar'));
 ft.find(n=>n.type==='button'&&n.props.children==='전체').props.onClick();ft=filters.render();assert(cardNames(ft).includes('Achernar'));
 console.log('PASS: visible gender filters and filter persistence across provider tabs; speaker gender mismatch requires explicit acknowledgment; recent confirmed order, persistence, account isolation, corrupt storage; initial provider tabs, single dialog, no automatic API calls, selection/cancel, preview cleanup and explicit sample');
})().catch(e=>{console.error(e);process.exitCode=1});
