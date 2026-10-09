const fs=require('fs'),path=require('path'),ts=require('typescript'),test=require('node:test'),assert=require('node:assert/strict')
const code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../components/StdSpeakerCoordinates.tsx'),'utf8'),{compilerOptions:{module:1,target:9,jsx:2}}).outputText
const face={speaker:'仙太郎',status:'visible',face_box:[.2,.2,.6,.6],mouth_box:[.4,.4,.45,.43]}
const scene={number:63,key:'same-image',image:{id:'image'},rows:[{speaker:'仙太郎',text:'父上。'},{speaker:'大五郎',text:'米俵が…'}]}
const uiExports={};new Function('exports',ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../lib/stdUiText.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText)(uiExports)
function harness(rows,locale='ko',overrideScene={},fetchError=''){
 const data={count:1,completed:0,confirmed:0,scenes:[{...scene,...overrideScene}]},state=[data,'',true,scene.key,'a'.repeat(64),0,63,rows,0,'mouth_box','blob:image',true,false,'',null];let cursor=0,submitted;const effects=[]
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),useState:()=>{const i=cursor++;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v}]},useEffect:(fn,deps)=>effects.push({fn,deps}),useCallback:f=>f,useRef:v=>({current:v})}
 const exports={};new Function('exports','require','React','document','fetch',code)(exports,n=>n==='react'?React:n==='../lib/stdUiText'?uiExports:{createPortal:node=>node},React,{body:{}},async(url,options)=>{submitted=JSON.parse(options.body);return{ok:!fetchError,json:async()=>fetchError?{error:fetchError}:data}})
 const render=()=>{cursor=0;return exports.default({projectId:'project',revision:'1',headers:{},locale})}
 const find=(node,predicate)=>{if(!node||typeof node!=='object')return null;if(predicate(node))return node;for(const child of (node.children||[]).flat(Infinity)){const found=find(child,predicate);if(found)return found}return null}
 const label=n=>(n.children||[]).flat(Infinity).filter(v=>typeof v==='string').join('')
 return{state,render,find,label,effects,get submitted(){return submitted}}
}
test('actual editor enables partial save and sends draft without losing the pending speaker',async()=>{
 const h=harness([face,{speaker:'大五郎',status:'unconfirmed'}]),tree=h.render()
 const button=h.find(tree,n=>n.type==='button'&&h.label(n)==='지정한 화자 위치 저장')
 assert.ok(button);assert.equal(button.props.disabled,false)
 assert.ok(h.find(tree,n=>n.type==='button'&&h.label(n).includes('大五郎')&&h.label(n).includes('미지정')))
 button.props.onClick();await new Promise(resolve=>setImmediate(resolve))
 assert.equal(h.submitted.draft,true);assert.equal(h.submitted.speakers.length,2);assert.match(uiExports.stdUiText('ko',h.state[13].text,h.state[13].values),/1명 위치를 저장/)
})
test('actual editor requires one completed speaker to save and all speakers to confirm',()=>{
 const empty=harness([{speaker:'仙太郎',status:'unconfirmed'},{speaker:'大五郎',status:'unconfirmed'}])
 assert.equal(empty.find(empty.render(),n=>n.type==='button'&&empty.label(n)==='지정한 화자 위치 저장').props.disabled,true)
 const complete=harness([face,{speaker:'大五郎',status:'offscreen'}])
 assert.equal(complete.find(complete.render(),n=>n.type==='button'&&complete.label(n)==='이 씬 화자 위치 확정').props.disabled,false)
})

function visibleText(node) {
 if(typeof node==='string')return node
 if(Array.isArray(node))return node.map(visibleText).join(' ')
 if(!node||typeof node!=='object')return ''
 return [node.props?.['aria-label'],node.props?.alt,visibleText(node.children)].filter(Boolean).join(' ')
}
test('Thai dialog covers incomplete, analyzed, failed, confirmed, queued and delayed states',()=>{
 const cases=[{}, {error:'face missing'}, {result:{origin:'user',speakers:[]}}, {result:{origin:'auto',speakers:[]}}, {analysisState:'queued'}, {analysisState:'processing',heartbeatAt:new Date().toISOString()}, {analysisState:'processing',heartbeatAt:'2020-01-01'}]
 for(const sceneState of cases){
  const h=harness([face,{speaker:'大五郎',status:'unconfirmed'}],'th',sceneState)
  const text=visibleText(h.render())
  assert.doesNotMatch(text,/[가-힣]/)
  assert.match(text,/กำหนดตำแหน่งใบหน้าและปาก/)
  assert.match(text,/仙太郎/);assert.match(text,/父上。/)
  h.state[11]=false;h.state[10]='';assert.match(visibleText(h.render()),/กำลังโหลดภาพต้นฉบับ/)
 }
})
test('Thai partial save, full confirmation and server validation messages stay localized',async()=>{
 for(const rows of [[face,{speaker:'大五郎',status:'unconfirmed'}],[face,{speaker:'大五郎',status:'offscreen'}]]){
  const h=harness(rows,'th'),button=h.find(h.render(),n=>n.type==='button'&&String(n.props.className).includes('bg-emerald-700'))
  assert.equal(button.props.disabled,false);button.props.onClick();await new Promise(resolve=>setImmediate(resolve))
  assert.doesNotMatch(visibleText(h.render()),/[가-힣]/)
  assert.match(visibleText(h.render()),rows[1].status==='offscreen'?/ยืนยันตำแหน่งผู้พูดในฉากที่ 63 แล้ว/:/บันทึกตำแหน่งแล้ว 1 คน/)
 }
 const h=harness([face,{speaker:'大五郎',status:'offscreen'}],'th',{},'입 영역은 얼굴 영역 안에 있어야 합니다.')
 h.find(h.render(),n=>n.type==='button'&&String(n.props.className).includes('bg-emerald-700')).props.onClick()
 await new Promise(resolve=>setImmediate(resolve))
 assert.match(visibleText(h.render()),/บริเวณปากต้องอยู่ภายในบริเวณใบหน้า/)
 assert.doesNotMatch(visibleText(h.render()),/[가-힣]/)
})

test('video-only scene prepares a reference instead of waiting forever for an image', async()=>{
 const h=harness([{speaker:'仙太郎',status:'unconfirmed'}],'ko',{image:null,video:{id:'original-video'}})
 h.render()
 const effect=h.effects.find(e=>e.deps.includes('same-image'))
 assert.ok(effect)
 const cleanup=effect.fn()
 await new Promise(resolve=>setImmediate(resolve))
 assert.equal(h.submitted.action,'prepare_video')
 assert.equal(h.submitted.videoId,'original-video')
 assert.equal(h.submitted.sceneNumber,63)
 cleanup()
})
