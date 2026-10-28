const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {root,load}=require('../scripts/std_web_runtime.cjs');
const out=path.join(root,'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package');
const c=JSON.parse(fs.readFileSync(path.join(out,'../candidate.json'),'utf8'));
const {splitTextToSingleLineChunks}=load('stdSubtitles');
const {splitSubtitleDialogueBlocks}=load('stdDialogueAnnotations');
const {normalizeSubtitleFragments,isSubtitleClosingPunctuation}=load('stdSubtitleFragments');
const rows=[];let cursor=0;
const compact=s=>s.replace(/[\s「」『』“”"']/gu,'');
for(const scene of c.structure.scenes){
 const text=scene.scene_text||scene.narration, n=scene.scene_number,d=scene.duration_seconds;
 const parts=splitSubtitleDialogueBlocks([{scene_number:n,text,start_num:cursor,end_num:cursor+d}],c.structure.dialogue_annotations,true,20);
 const chunks=parts.flatMap(p=>splitTextToSingleLineChunks(p.text,20,{dialogue:p.dialogue_kind==='dialogue'}).map(text=>({...p,text})));
 const weight=chunks.reduce((a,x)=>a+Array.from(x.text).length,0);let at=cursor;
 chunks.forEach((p,i)=>{const end=i===chunks.length-1?cursor+d:at+d*Array.from(p.text).length/weight;rows.push({...p,id:`jp-life-sub-${n}-${i+1}`,start_num:at,end_num:end,start_time:String(at),end_time:String(end),image_url:'',video_url:null,is_hook_zone:n<=18});at=end;});
 cursor+=d;
}
const normalized=normalizeSubtitleFragments(rows,20);
for(const scene of c.structure.scenes){assert.equal(compact(normalized.filter(x=>x.scene_number===scene.scene_number).map(x=>x.text).join('')),compact(scene.scene_text||scene.narration));}
assert.equal(cursor,1961);assert(!normalized.some(x=>isSubtitleClosingPunctuation(x.text)));assert.equal(new Set(normalized.map(x=>x.scene_number)).size,136);
fs.writeFileSync(path.join(out,'subtitles.json'),JSON.stringify(normalized,null,2));
console.log(JSON.stringify({blocks:normalized.length,scenes:136,end:cursor,dialogue_blocks:normalized.filter(x=>x.dialogue_kind==='dialogue').length}));
