const fs=require('node:fs'),path=require('node:path'),ts=require('../node_modules/typescript');
const cache=new Map();
function load(file){
 const full=path.resolve(file);if(cache.has(full))return cache.get(full);
 const out={};cache.set(full,out);
 const code=ts.transpileModule(fs.readFileSync(full,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 new Function('exports','require',code)(out,id=>{
  if(id.startsWith('.')||id.startsWith('@/')){const base=id.startsWith('@/')?path.resolve(__dirname,'..',id.slice(2)):path.resolve(path.dirname(full),id);const found=['','.ts','.tsx'].map(ext=>base+ext).find(p=>fs.existsSync(p)&&fs.statSync(p).isFile());return load(found);}
  return require(id);
 });return out;
}
module.exports=load;
