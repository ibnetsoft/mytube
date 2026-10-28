const fs=require('fs'),path=require('path'),cp=require('child_process'),assert=require('assert/strict');
const r=require('../scripts/std_web_runtime.cjs');const dir=path.join(r.root,'_dev/artifacts/v4-performance');
const receipt=JSON.parse(fs.readFileSync(path.join(dir,'live-receipt.json')));
async function main(){
 const snapshot=JSON.parse(fs.readFileSync(path.join(dir,'live-snapshot.json')));
 const assets=snapshot.assets,final=assets.find(a=>a.asset_type==='audio'&&a.status==='uploaded');
 assert(final,'No finalized audio yet');
 const timeline=final.metadata.subtitle_timeline;assert.equal(timeline.length,receipt.texts.length);
 const db=r.load('supabaseAdmin').supabaseAdmin;
 const keys=await r.load('elevenLabsKeys').getConfiguredElevenLabsKeys();
 const history=[];
 const matches=new Map();
 const spoken=receipt.texts; receipt.texts=spoken.map((text,i)=>'['+receipt.tags[i][0]+'] '+text);
 for(let slot=0;slot<Math.min(keys.length,2) && matches.size<receipt.texts.length;slot++){
  const url=new URL('https://api.elevenlabs.io/v1/history');url.searchParams.set('voice_id',receipt.voiceId);url.searchParams.set('date_after_unix',String(Math.floor(Date.parse(receipt.createdAt)/1000)));url.searchParams.set('source','TTS');url.searchParams.set('page_size','20');
  const res=await fetch(url,{headers:{'xi-api-key':keys[slot]}});
  if(!res.ok){console.log(`History key slot ${slot+1}: HTTP ${res.status}`);continue;}
  const body=await res.json();
  for(const h of body.history||[]){for(const input of (h.dialogue?.length ? h.dialogue : [{text:h.text,voice_id:h.voice_id}])){if(receipt.texts.includes(input.text)&&input.voice_id===receipt.voiceId&&!matches.has(input.text))matches.set(input.text,{...h,text:input.text,voice_id:input.voice_id,keySlot:slot+1});}}
  console.log(`History key slot ${slot+1}: ${(body.history||[]).length} rows, ${matches.size} sample matches; latest=${body.history?.[0]?.date_unix}`);
 }
 for(const text of receipt.texts){
  const match=matches.get(text);assert(match,'Provider history missing exact sample text');assert.equal(match.model_id,'eleven_v4');
  const details=await (await fetch(`https://api.elevenlabs.io/v1/history/${match.history_item_id}`,{headers:{'xi-api-key':keys[match.keySlot-1]}})).json();
  history.push({id:match.history_item_id,model:match.model_id,voiceId:match.voice_id,text:match.text,dateUnix:match.date_unix,keySlot:match.keySlot,alignments:details.alignments});
 }
 fs.writeFileSync(path.join(dir,'provider-history.json'),JSON.stringify(history,null,2)); receipt.texts=spoken;
 const download=r.load('gcsStorage').downloadGcsObject;
 const read=async a=>{const buffer=await download({bucket:a.metadata.gcs_bucket||a.metadata.storage_bucket,objectPath:a.metadata.gcs_path||a.metadata.storage_path});return Buffer.isBuffer(buffer)?buffer:Buffer.from(buffer)};
 const audio=await read(final);fs.writeFileSync(path.join(dir,'v4-live-sample.mp3'),audio);
 const segments=[];
 for(let i=0;i<timeline.length;i++){const row=timeline[i];assert.equal(row.text,receipt.texts[i]);const asset=assets.find(a=>a.metadata?.kind==='vrew_segment_tts'&&a.metadata.text===row.text);assert(asset);assert.equal(asset.metadata.model_id,'eleven_v4');const clip=await read(asset);segments.push(clip);fs.writeFileSync(path.join(dir,`v4-${receipt.tags[i][0]}.mp3`),clip);assert.deepEqual(asset.metadata.voice_performance.cues,[{offset:0,tag:receipt.tags[i][0]}]);assert.equal(row.start,i?timeline[i-1].end:0);}
 const assembled=await r.load('stdNarrationMp3').finalizeNarrationMp3(segments);
 const discrepancies=timeline.map((row,i)=>({text:row.text,start:row.start,end:row.end,actualClipDuration:assembled.durations[i],boundaryErrorMs:Math.abs((row.end-row.start)-assembled.durations[i])*1000}));
 discrepancies.forEach(d=>assert(d.boundaryErrorMs<1));
 const pcm=cp.execFileSync(process.env.FFMPEG_PATH,['-v','error','-i',path.join(dir,'v4-live-sample.mp3'),'-f','s16le','-ar','44100','-ac','1','pipe:1']);
 const decodedDuration=pcm.length/2/44100,total=timeline.at(-1).end,driftMs=Math.abs(total-decodedDuration)*1000;assert(driftMs<40);
 const savedRows=snapshot.project.project_payload.subtitles;
 timeline.forEach((row,i)=>{assert.equal(Number(savedRows[i].start_num),row.start);assert.equal(Number(savedRows[i].end_num),row.end)});
 const stamp=n=>new Date(Math.round(n*1000)).toISOString().slice(11,23).replace('.',',');
 fs.writeFileSync(path.join(dir,'v4-live-sample.srt'),timeline.map((row,i)=>`${i+1}\n${stamp(row.start)} --> ${stamp(row.end)}\n${row.text}\n`).join('\n'));
 const result={tags:receipt.tags,providerTaggedInputsConfirmed:true,subtitleTagsAbsent:timeline.every(row=>!/[\[\]]/.test(row.text)),projectId:receipt.projectId,models:history.map(h=>h.model),duration:total,decodedDuration,driftMs,discrepancies,savedSubtitleTimingMatches:true};
 fs.writeFileSync(path.join(dir,'audio-verification.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
