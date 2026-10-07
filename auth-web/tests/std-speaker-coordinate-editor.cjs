const fs=require('fs'),path=require('path'),ts=require('typescript'),test=require('node:test'),assert=require('node:assert/strict')
const code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../components/StdSpeakerCoordinates.tsx'),'utf8'),{compilerOptions:{module:1,target:9,jsx:2}}).outputText
const face={speaker:'仙太郎',status:'visible',face_box:[.2,.2,.6,.6],mouth_box:[.4,.4,.45,.43]}
const scene={number:63,key:'same-image',image:{id:'image'},rows:[{speaker:'仙太郎',text:'父上。'},{speaker:'大五郎',text:'米俵が…'}]}
function harness(rows){
 const data={count:1,completed:0,confirmed:0,scenes:[scene]},state=[data,'',true,scene.key,'a'.repeat(64),0,63,rows,0,'mouth_box','blob:image',true,false,'',null];let cursor=0,submitted
 const React={createElement:(type,props,...children)=>({type,props:props||{},children}),useState:()=>{const i=cursor++;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v}]},useEffect:()=>{},useCallback:f=>f,useRef:v=>({current:v})}
 const exports={};new Function('exports','require','React','document','fetch',code)(exports,n=>n==='react'?React:{createPortal:node=>node},React,{body:{}},async(url,options)=>{submitted=JSON.parse(options.body);return{ok:true,json:async()=>data}})
 const render=()=>{cursor=0;return exports.default({projectId:'project',revision:'1',headers:{}})}
 const find=(node,predicate)=>{if(!node||typeof node!=='object')return null;if(predicate(node))return node;for(const child of (node.children||[]).flat(Infinity)){const found=find(child,predicate);if(found)return found}return null}
 const label=n=>(n.children||[]).flat(Infinity).filter(v=>typeof v==='string').join('')
 return{state,render,find,label,get submitted(){return submitted}}
}
test('actual editor enables partial save and sends draft without losing the pending speaker',async()=>{
 const h=harness([face,{speaker:'大五郎',status:'unconfirmed'}]),tree=h.render()
 const button=h.find(tree,n=>n.type==='button'&&h.label(n)==='지정한 화자 위치 저장')
 assert.ok(button);assert.equal(button.props.disabled,false)
 assert.ok(h.find(tree,n=>n.type==='button'&&h.label(n).includes('大五郎')&&h.label(n).includes('미지정')))
 button.props.onClick();await new Promise(resolve=>setImmediate(resolve))
 assert.equal(h.submitted.draft,true);assert.equal(h.submitted.speakers.length,2);assert.match(h.state[13],/1명 위치를 저장/)
})
test('actual editor requires one completed speaker to save and all speakers to confirm',()=>{
 const empty=harness([{speaker:'仙太郎',status:'unconfirmed'},{speaker:'大五郎',status:'unconfirmed'}])
 assert.equal(empty.find(empty.render(),n=>n.type==='button'&&empty.label(n)==='지정한 화자 위치 저장').props.disabled,true)
 const complete=harness([face,{speaker:'大五郎',status:'offscreen'}])
 assert.equal(complete.find(complete.render(),n=>n.type==='button'&&complete.label(n)==='이 씬 화자 위치 확정').props.disabled,false)
})
