const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), ts = require('typescript')
const code = ts.transpileModule(fs.readFileSync('auth-web/components/SubtitleSfxPicker.tsx','utf8'), {compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText
test('popup immediately lists uploaded file even while parent still holds older catalog', async()=>{
    const states=[[],false,true,'','','','',''];let cursor=0
    const react={useState:initial=>{const i=cursor++;if(states[i]===undefined)states[i]=initial;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v]},useEffect:()=>{},useRef:()=>({current:null})}
    const jsx=(type,props)=>({type,props});const output={}
    new Function('exports','require',code)(output,id=>id==='react'?react:id==='react/jsx-runtime'?{jsx,jsxs:jsx}:id==='react-dom'?{createPortal:x=>x}:id.includes('stdUiText')?{stdUiText:(_,text)=>text}:{sfxDescriptionKo:()=>''})
    global.document={body:{}}
    const props={assets:[{id:'old',file_name:'old.mp3'}],value:'',projectId:'p',headers:{},onChange:()=>{},onOpen:()=>{},onUpload:async()=>({id:'new',file_name:'knock.mp3'})}
    const render=()=>{cursor=0;return output.default(props)}
    const nodes=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)]
    const input=nodes(render()).find(n=>n.type==='input'&&n.props.type==='file')
    await input.props.onChange({target:{files:[{name:'knock.mp3'}],value:'file'}})
    assert.equal(states[4],'new')
    assert.ok(JSON.stringify(render()).includes('knock.mp3'))
    delete global.document
})
