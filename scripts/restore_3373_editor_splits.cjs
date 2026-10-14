const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
process.loadEnvFile(path.resolve('.env'));
const { createClient } = require('../auth-web/node_modules/@supabase/supabase-js');
const ts = require('../auth-web/node_modules/typescript');
function load(name) { const out = {}; new Function('exports', 'require', ts.transpileModule(fs.readFileSync(path.join('auth-web/lib', name+'.ts'),'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(out, require); return out; }
const {normalizeSubtitleFragments} = load('stdSubtitleFragments');
const {preserveSubtitleScenes} = load('stdSubtitleSceneIntegrity');
async function main() {
 const id='e9233112-f0d7-4b35-91bf-2f892844eb30', db=createClient(process.env.NEXT_PUBLIC_SUPABASE_URL,process.env.SUPABASE_SERVICE_ROLE_KEY);
 const {data:p,error}=await db.from('std_projects').select('*').eq('id',id).single(); if(error)throw error;
 const old=JSON.parse(fs.readFileSync('output/project-recovery-e9233112/before-13min-recovery-project.json','utf8')).project_payload;
 const payload=p.project_payload, original=payload.subtitles, recovered=original.filter(r=>/^sub-\d+-source-recovery$/.test(r.id));
 if(!recovered.length) throw Error('No recovery placeholders; do not repeat this repair.');
 const norm=t=>String(t).replace(/\s/gu,'');
 const replacements=new Map();
 for(const row of recovered) {
  const saved=old.subtitles.filter(r=>Number(r.scene_number)===Number(row.scene_number));
  assert(saved.length, `Missing backup scene ${row.scene_number}`);
  assert.equal(norm(saved.map(r=>r.text).join('')),norm(row.text),`Changed source scene ${row.scene_number}`);
  replacements.set(Number(row.scene_number),saved.map(r=>({...r,restored_audio_pending:true,audio_regeneration_required:true,
   voice_assignment_pending:r.dialogue_kind==='dialogue' && !r.editor_speaker?.name,
   editor_recovery:{source:'before-13min-recovery-project.json',recording_verified:false}})));
 }
 const rows=normalizeSubtitleFragments(original.flatMap(r=>replacements.get(Number(r.scene_number))||[r]),20,{punctuationOnly:true});
 assert.equal(rows.filter(r=>/^sub-\d+-source-recovery$/.test(r.id)).length,0);
 for(const row of original.filter(r=>!replacements.has(Number(r.scene_number)))) assert.deepEqual(rows.find(r=>r.id===row.id),row);
 const jobs=await db.from('std_subtitle_translation_jobs').select('target_language,result_blocks,created_at').eq('project_id',id).eq('translation_kind','subtitles').eq('status','completed'); if(jobs.error)throw jobs.error;
 const translations={};
 for(const language of ['ko','th']) {
  const byText=new Map();
  for(const b of old.subtitle_translations?.[language]?.blocks||[])if(b.translated_text)byText.set(b.source_text.trim(),b.translated_text);
  for(const job of jobs.data.filter(j=>j.target_language===language).sort((a,b)=>a.created_at.localeCompare(b.created_at)))for(const b of job.result_blocks||[])if(b.translated_text)byText.set(b.source_text.trim(),b.translated_text);
  for(const b of payload.subtitle_translations?.[language]?.blocks||[])if(b.translated_text)byText.set(b.source_text.trim(),b.translated_text);
  translations[language]={version:1,updated_at:new Date().toISOString(),blocks:rows.flatMap((r,index)=>{const source_text=r.text.trim(),translated_text=byText.get(source_text);return translated_text?[{index,source_text,translated_text}]:[]})};
 }
 const updated={...payload,subtitles:rows,subtitle_editor_snapshot:rows,subtitle_translations:translations,
  subtitle_editor_recovery:{restored_at:new Date().toISOString(),scene_numbers:[...replacements.keys()],backup:'before-13min-recovery-project.json',audio_preserved:true}};
 const evidence={scenes:replacements.size,rows:rows.length,speakers:rows.filter(r=>r.editor_speaker?.name).length,translations:Object.fromEntries(Object.entries(translations).map(([k,v])=>[k,v.blocks.length]))};
 fs.writeFileSync('output/project-recovery-e9233112/before-editor-split-restoration.json',JSON.stringify(p));
 fs.writeFileSync('output/project-recovery-e9233112/editor-split-restoration-candidate.json',JSON.stringify(updated));
 const result=await db.from('std_projects').update({project_payload:updated,progress_payload:{...p.progress_payload,subtitles_saved:true,subtitle_tts_completed:false,subtitles_completed:false},updated_at:new Date().toISOString()}).eq('id',id).eq('updated_at',p.updated_at).select('id').single(); if(result.error)throw result.error;
 const verified=await db.from('std_projects').select('project_payload').eq('id',id).single();if(verified.error)throw verified.error;
 assert.deepEqual(verified.data.project_payload.subtitles,rows);
 assert.deepEqual(verified.data.project_payload.voice_segments,payload.voice_segments);
 assert.equal(verified.data.project_payload.audio_url,payload.audio_url);
 assert.deepEqual(preserveSubtitleScenes(original,rows,[]).subtitles,rows);
 assert.deepEqual(preserveSubtitleScenes(rows,rows,[]).subtitles,rows);
 fs.writeFileSync('output/project-recovery-e9233112/editor-split-restoration-verification.json',JSON.stringify(evidence,null,2));
 console.log(JSON.stringify(evidence));
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
