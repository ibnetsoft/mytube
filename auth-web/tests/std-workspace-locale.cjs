const assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('../node_modules/typescript');
const load=require('./load-ts-module.cjs');
const {stdUiText}=load('auth-web/lib/stdUiText.ts');
const {STD_WORKSPACE_COPY}=load('auth-web/lib/stdWorkspaceLocale.ts');
for(const [locale,copy] of Object.entries(STD_WORKSPACE_COPY)){
 if(locale==='ko')continue;
 for(const [key,value]of Object.entries(copy)){
  assert.ok(value.trim(),`${locale}: ${key}`);
  assert.deepEqual([...key.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort(),[...value.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort(),`${locale} placeholders: ${key}`);
 }
 assert.equal(stdUiText(locale,'unregistered user content'),'unregistered user content');
 assert.ok(!/[가-힣]/.test(stdUiText(locale,'성우 미지정 {missing}개 · 내레이션 성우와 겹침 {shared}개',{missing:98,shared:0})));
}
const page=fs.readFileSync('auth-web/app/std/page.tsx','utf8');const ast=ts.createSourceFile('page.tsx',page,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
assert.equal(ast.parseDiagnostics.length,0);
let translated=0;
function visit(n){
 const l=ast.getLineAndCharacterOfPosition(n.getStart()).line+1;
 if(((l>=8937&&l<10438)||(l>=11091&&l<11944)||(l>=12139&&l<12531)||l>=12889)&&ts.isCallExpression(n)&&n.expression.getText(ast)==='ui'&&ts.isStringLiteral(n.arguments[0])){
  const value=n.arguments[0].text;if(/[가-힣]/.test(value))for(const locale of ['en','vi','th'])assert.notEqual(stdUiText(locale,value),value,`${locale} untranslated: ${value}`);translated++;
 }
 if(ts.isJsxAttribute(n)&&n.name.text==='value'&&n.initializer)assert.ok(!/^\{ui\(/.test(n.initializer.getText(ast)),'Persisted values must not be translated');
 ts.forEachChild(n,visit);
}
visit(ast);assert.ok(translated>200);
assert.match(page,/<StdTtsReadinessNotice\s+locale=\{currentLocale\}/);
console.log('PASS: all requested screen labels in EN/VI/TH, placeholders, source content and persisted identifiers');
const React=require('../node_modules/react'),{renderToStaticMarkup}=require('../node_modules/react-dom/server');
const Notice=load('auth-web/components/StdTtsReadinessNotice.tsx').default;
for(const locale of ['ko','en','vi','th']){
 const html=renderToStaticMarkup(React.createElement(Notice,{locale,busy:false,compact:true,
  subtitles:[{scene_number:2,text:'「伏せろ！」'}],readiness:{ready:false,issues:[{index:0,reason:'missing'}]},voices:new Map(),onJump:()=>{}}));
 assert.ok(html.includes('「伏せろ！」'));assert.ok(html.includes(stdUiText(locale,'씬 {scene} · 자막 {subtitle}',{scene:2,subtitle:1})));
 if(locale!=='ko')assert.ok(!/[가-힣]/.test(html),locale+' screenshot notice remains Korean');
}
console.log('PASS: actual missing-voice notice localized without changing Japanese subtitle text');
