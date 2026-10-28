const fs=require('fs'),path=require('path'),{createRequire}=require('module');
const root=path.resolve(__dirname,'..'),web=path.join(root,'auth-web'),req=createRequire(path.join(web,'package.json'));
for(const f of ['.env','.env.local','auth-web/.env.local']){const p=path.join(root,f);if(fs.existsSync(p))process.loadEnvFile(p);}
const ts=req('typescript'),cache={};
function load(name){if(cache[name])return cache[name];const ex={};cache[name]=ex;const file=path.join(web,'lib',name+'.ts'),localReq=createRequire(file);new Function('exports','require',ts.transpile(fs.readFileSync(file,'utf8'),{module:1,target:7}))(ex,n=>n.startsWith('./')&&fs.existsSync(path.resolve(path.dirname(file),n)+'.ts')?load(n.slice(2)):localReq(n));return ex;}
(async()=>{
 const db=load('supabaseAdmin').supabaseAdmin,pid='e9233112-f0d7-4b35-91bf-2f892844eb30';
 const p=await db.from('std_projects').select('*').eq('id',pid).single();if(p.error)throw p.error;
 if(['approved','canceled'].includes(p.data.status))throw Error('Project is closed');
 if(p.data.progress_payload?.script_changed_requires_audio_regeneration)throw Error('TTS regeneration required');
 const [s,a]=await Promise.all([db.from('std_project_scenes').select('*').eq('project_id',pid).order('scene_number'),db.from('std_project_assets').select('*').eq('project_id',pid).in('status',['uploaded','assigned'])]);
 if(s.error||a.error)throw s.error||a.error;
 const audios=a.data.filter(x=>x.asset_type==='audio').sort((x,y)=>String(y.created_at).localeCompare(String(x.created_at)));
 for(const audio of audios){const timeline=audio.metadata?.subtitle_timeline||[],subs=p.data.project_payload.subtitles||[];const mismatch=subs.flatMap((row,i)=>{const t=timeline[i]||{};const fields=[];if(row.text?.trim()!==t.text?.trim())fields.push('text');if(String(row.voice_id||row.voiceId||'')!==String(t.voice_id||''))fields.push('voice');if(Math.abs(Number(row.start??row.start_num??row.start_time)-Number(t.start))>.12||Math.abs(Number(row.end??row.end_num??row.end_time)-Number(t.end))>.12)fields.push('timing');return fields.length?[{index:i,fields,voice:row.voice_id||row.voiceId||'',recorded_voice:t.voice_id,start:row.start??row.start_num??row.start_time,recorded_start:t.start}]:[];});console.log(JSON.stringify({audio_id:audio.id,created_at:audio.created_at,subtitles:subs.length,timeline:timeline.length,mismatch_count:mismatch.length,sample:mismatch.slice(0,3)}));}
 const audio=audios[0],timeline=audio?.metadata?.subtitle_timeline,subs=p.data.project_payload.subtitles;
 if(!timeline||timeline.length!==subs.length)throw Error('Missing recorded subtitle timing');
 subs.forEach((row,i)=>{const t=timeline[i],segment=audio.metadata.voice_segments?.[i];if(row.text?.trim()!==t.text?.trim()||String(row.voice_id||row.voiceId||'')!==String(t.voice_id||'')||!Number.isFinite(t.start)||!Number.isFinite(t.end)||t.end<=t.start||(segment&&String(row.direction||'')!==String(segment.direction||'')))throw Error('Recording differs from saved dialogue; no timing repair allowed');});
 const needsTiming=subs.some((row,i)=>Math.abs(Number(row.start??row.start_num??row.start_time)-timeline[i].start)>.12||Math.abs(Number(row.end??row.end_num??row.end_time)-timeline[i].end)>.12);
 if(needsTiming){
  fs.writeFileSync(path.join(root,'_dev/artifacts/image_repair_3373/ae-timing.before.json'),JSON.stringify(p.data,null,2));
  const aligned=subs.map((row,i)=>{const next={...row,start:timeline[i].start,end:timeline[i].end};for(const k of ['start_num','start_time'])if(k in row)next[k]=timeline[i].start;for(const k of ['end_num','end_time'])if(k in row)next[k]=timeline[i].end;return next;});
  const update=await db.from('std_projects').update({project_payload:{...p.data.project_payload,subtitles:aligned},updated_at:new Date().toISOString()}).eq('id',pid).eq('updated_at',p.data.updated_at).select('*').maybeSingle();
  if(update.error||!update.data)throw Error('Project changed before timing repair');p.data=update.data;
  console.log('Restored subtitle display timing from unchanged recorded TTS: '+aligned.length);
 }
 const result=await load('stdAeMouthQueue').ensureAeMouthJob(p.data,s.data,a.data,process.argv.includes('--retry'));
 const old=a.data.filter(x=>x.metadata?.kind==='ae_mouth_job').sort((x,y)=>String(y.created_at).localeCompare(String(x.created_at)))[0];
 if(!result.job||result.job.id===old.id)throw Error('Expected corrected timing fingerprint');
 fs.writeFileSync(path.join(root,'_dev/artifacts/image_repair_3373/ae-corrected-retry.before.json'),JSON.stringify(old,null,2));
 const targets=new Set([23,24,25,30,32,33,36,39,42,43,45,47,62,96,98,100]);
 const rows=old.metadata.results.map(r=>targets.has(r.number)?{...r,status:'direction_approved',duration:result.job.metadata.input.scenes.find(s=>s.number===r.number).end-result.job.metadata.input.scenes.find(s=>s.number===r.number).start}:r);
 const update=await db.from('std_project_assets').update({metadata:{...result.job.metadata,state:'direction_approved',phase:'render',results:rows,timing_fix_version:2,previous_job:old.id},updated_at:new Date().toISOString()}).eq('id',result.job.id).eq('updated_at',result.job.updated_at).select('*').single();
 if(update.error)throw update.error;result.job=update.data;
 const receipt={job_id:result.job?.id,state:result.job?.metadata?.state,ready:result.ready,scene_count:result.job?.metadata?.input?.scenes?.length};
 fs.writeFileSync(path.join(root,'_dev/artifacts/image_repair_3373/ae-enqueue.receipt.json'),JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));
})().catch(e=>{console.error(e.message);process.exitCode=1;});
