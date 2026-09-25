const fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.resolve(__dirname,'..');
const requireWeb=require('module').createRequire(path.join(root,'auth-web/package.json'));
const ts=requireWeb('typescript');
const out=path.join(root,'output/repair-3292-20260915');
function load(file){const box={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,'auth-web/lib',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:box,exports:box.exports,require});return box.exports;}
const utils=load('stdSubtitles.ts'),dialogue=load('stdDialogueAnnotations.ts');
const structure=JSON.parse(fs.readFileSync(path.join(out,'staged-structure.json'),'utf8'));
const annotations=JSON.parse(fs.readFileSync(path.join(out,'dialogue-annotations.json'),'utf8'));
const script=structure.scenes.map(s=>s.scene_text).join('\n\n');
// Existing generator drops ellipses; retain approved source characters verbatim.
const base=[];
for(const scene of structure.scenes){
 const words=scene.scene_text.match(/\S+\s*/gu)||[];const chunks=[];let current='';
 for(const word of words){if(current&&Array.from(current+word).length>20){chunks.push(current);current='';}current+=word;}
 if(current)chunks.push(current);
 let offset=0;const count=Array.from(scene.scene_text).length;
 chunks.forEach((text,i)=>{const from=scene.start_time+scene.duration_seconds*offset/count;offset+=Array.from(text).length;const to=i===chunks.length-1?scene.end_time:scene.start_time+scene.duration_seconds*offset/count;base.push({id:`3292-sub-${scene.scene_number}-${i+1}`,scene_number:scene.scene_number,start_num:from,end_num:to,start_time:String(from),end_time:String(to),text,image_url:'',video_url:null,is_hook_zone:scene.scene_number<=12});});
}
const rows=dialogue.splitSubtitleDialogueBlocks(base,annotations);
const compact=s=>s.replace(/[\s"'“”‘’「」『』]/gu,'');
for(const scene of structure.scenes){const parts=rows.filter(r=>r.scene_number===scene.scene_number);if(compact(parts.map(r=>r.text).join(''))!==compact(scene.scene_text))throw new Error('Subtitle text differs '+scene.scene_number+': '+JSON.stringify({original:scene.scene_text,actual:parts.map(r=>r.text).join('')}));}
if(new Set(rows.map(r=>r.scene_number)).size!==53||Math.abs(rows.at(-1).end_num-900)>0.01)throw new Error('Invalid scene/time count');
fs.writeFileSync(path.join(out,'subtitles.json'),JSON.stringify(rows,null,2));
console.log(JSON.stringify({blocks:rows.length,scenes:53,end:rows.at(-1).end_num}));
