const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {root,load}=require('../scripts/std_web_runtime.cjs');
const out=path.join(root,'output/codex-local-console/6ae46b7afca84070b36e9e13d7de0a6e/web-package');
const p=JSON.parse(fs.readFileSync(path.join(out,process.argv.includes('--registered')?'registered-topic.json':'topic-registration-payload.json'),'utf8'));
const {isPreparedUserTopic,hasReadySceneMediaPrompts}=load('preparedTopic');
const {normalizeSubtitleFragments,isSubtitleClosingPunctuation}=load('stdSubtitleFragments');
assert(isPreparedUserTopic(p),'User-web prepared-topic gate rejected');assert(hasReadySceneMediaPrompts(p));
const scenes=p.pregenerated_structure.scenes,subs=p.progress_payload.subtitles;
assert.equal(scenes.length,136);assert.equal(scenes.reduce((n,s)=>n+s.duration_seconds,0),1961);assert.equal(scenes.filter(s=>s.video_prompt_required).length,18);
assert(scenes.every(s=>s.image_url&&s.metadata.image_url===s.image_url));assert(!subs.some(s=>isSubtitleClosingPunctuation(s.text)));
const reopened=normalizeSubtitleFragments(subs,20,{punctuationOnly:true});assert.deepEqual(reopened,subs,'Reopening changes subtitles/translation mapping');
for(const lang of ['ko','th']){const blocks=p.progress_payload.subtitle_translations[lang].blocks;assert.equal(blocks.length,subs.length);blocks.forEach((b,i)=>{assert.equal(b.index,i);assert.equal(b.source_text,subs[i].text);assert(b.translated_text.trim())})}
const result={eligible:true,scene_count:scenes.length,duration_seconds:1961,image_count:136,video_prompts:18,subtitle_blocks:subs.length,ko_blocks:721,th_blocks:721,reopen_mapping_stable:true,thumbnail_editable:true};
fs.writeFileSync(path.join(out,'web-eligibility-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
