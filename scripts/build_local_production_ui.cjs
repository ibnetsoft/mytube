const fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),web=path.join(root,'auth-web'),out=path.join(root,'worker/local_production_ui');
const req=createRequire(path.join(web,'package.json'));
(async()=>{
    await req('esbuild').build({entryPoints:[path.join(out,'source.tsx')],outfile:path.join(out,'production-settings.js'),bundle:true,minify:true,format:'iife',platform:'browser',jsx:'automatic',target:'chrome110',nodePaths:[path.join(web,'node_modules')],alias:{'@':web},define:{'process.env.NODE_ENV':'"production"'},plugins:[{name:'local-dynamic',setup(build){build.onResolve({filter:/^next\/dynamic$/},()=>({path:'dynamic',namespace:'local'}));build.onLoad({filter:/.*/,namespace:'local'},()=>({contents:'import React from "react";export default function dynamic(loader){const Component=React.lazy(loader);return props=>React.createElement(React.Suspense,{fallback:React.createElement("p",null,"편집기 불러오는 중…")},React.createElement(Component,props))}',resolveDir:web,loader:'js'}))}}]});
    const {compile,optimize}=req('@tailwindcss/node'),{Scanner}=req('@tailwindcss/oxide');
    const compiler=await compile('@import "tailwindcss" source(none);',{base:web,onDependency:()=>{}});
    const scanner=new Scanner({sources:[{base:web,pattern:'components/Std*.tsx',negated:false},{base:out,pattern:'source.tsx',negated:false}]});
    fs.writeFileSync(path.join(out,'production-settings.css'),optimize(compiler.build(scanner.scan()),{minify:true}).code);
    console.log('Built native unified worker settings UI.');
})().catch(e=>{console.error(e);process.exitCode=1});
