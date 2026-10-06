const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript');
test('preview consumes exact saved render bitmap and never displays it for changed layers',async()=>{
 const effects=[];let redraws=0;
 const React={useEffect:f=>effects.push(f),useState:v=>[v,()=>{}]};
 const jsx={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'fragment'};
 const e={};const code=ts.transpileModule(fs.readFileSync(require.resolve('../components/StdTemplateOverlay.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 new Function('exports','require','document',code)(e,n=>n==='react'?React:n==='react/jsx-runtime'?jsx:{drawTemplateOverlay:async()=>{redraws++}}, {createElement:()=>({toDataURL:()=> 'new-bitmap'})});
 const layers=[{id:'title',text:'AIで生成された映像です',x:14,y:8,fontSize:12,fontFamily:'Pretendard'}];const saved='data:image/png;base64,exact-render-pixels';
 let rendered=e.default({layers,savedLayers:layers,savedImage:saved});assert.equal(rendered.props.children[0].props.src,saved);effects.splice(0).forEach(f=>f());assert.equal(redraws,0);
 rendered=e.default({layers:[{...layers[0],fontSize:14}],savedLayers:layers,savedImage:saved});assert.equal(rendered.props.children[0],'');effects.splice(0).forEach(f=>f());await Promise.resolve();assert.equal(redraws,1);
});
