const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{execFile}=require('node:child_process'),{promisify}=require('node:util');
const rt=require('./std_web_runtime.cjs'),db=rt.load('supabaseAdmin').supabaseAdmin,run=promisify(execFile);
const folder=path.resolve('output/codex-local-console/two-topic-mouths/3376/final-voice'),plan=JSON.parse(fs.readFileSync(path.join(folder,'voice-plan.json'),'utf8'));
const id='05e173f1-46a4-42e6-b543-6d7ba4458368',ffmpeg=path.resolve('venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe');
const progress=x=>{fs.writeFileSync(path.join(folder,'aligned-narration-progress.json'),JSON.stringify({...x,time:new Date().toISOString()}));console.log(JSON.stringify(x))};
async function main(){
 const {data:p,error}=await db.from('std_projects').select('*').eq('id',id).single();if(error)throw error;
 assert.deepEqual(p.project_payload.subtitles.map(s=>[s.text,s.voice_id]),plan.rows.map(s=>[s.text,s.voice_id]));
 const cache=rt.load('stdSegmentAudioCache'),keys=await rt.load('elevenLabsKeys').getConfiguredElevenLabsKeys();assert(keys[0]);
 const {data:existing,error:e}=await db.from('std_project_assets').select('metadata').eq('project_id',id).eq('metadata->>kind','vrew_segment_tts').in('status',['uploaded','assigned']).limit(1000);if(e)throw e;
 const cached=new Set(existing.map(a=>a.metadata.cache_key));
 const identity=s=>({text:s.text,provider:'elevenlabs',voiceId:s.voice_id,modelId:'eleven_multilingual_v2',speed:Number(p.project_payload.tts_speed)||1,direction:s.voice_direction||'',stability:.7,style:.45,language:p.language||'ja'});
 async function save(s,index,out){
  const ident=identity(s),key=cache.segmentAudioKey(ident);if(cached.has(key))return;
  for(let attempt=0;attempt<3;attempt++){
   try{const asset=await cache.persistSegmentAudio(db,{projectId:id,project:p,cacheKey:key,identity:ident,audioBuffer:fs.readFileSync(out),fileName:`aligned-narration-${index+1}.mp3`,segmentIndex:index,generatedBy:p.employee_email});assert(asset.id);cached.add(key);return}
   catch(error){const found=await db.from('std_project_assets').select('id').eq('project_id',id).eq('metadata->>cache_key',key).limit(1);if(found.data?.length){cached.add(key);return}if(attempt===2)throw error;await new Promise(r=>setTimeout(r,1000))}
  }
 }
 let recovered=0;
 for(const name of fs.readdirSync(folder).filter(n=>n.startsWith('aligned-'))){const d=path.join(folder,name);if(!fs.statSync(d).isDirectory())continue;const receipt=path.join(d,'alignment.json');if(!fs.existsSync(receipt))continue;const alignedText=JSON.parse(fs.readFileSync(receipt,'utf8')).characters.join('');for(const file of fs.readdirSync(d)){const match=/^row-(\d+)\.mp3$/.exec(file);if(!match)continue;const index=Number(match[1]),row=plan.rows[index];assert(row?.voice_id===plan.narrator&&alignedText.includes(row.text));if(!cached.has(cache.segmentAudioKey(identity(row)))){await save(row,index,path.join(d,file));recovered++}}}
 if(recovered)progress({phase:'recovered_saved_audio',rows:recovered});
 const groups=[];let current=[];let chars=0;
 const flush=()=>{if(current.length)groups.push(current);current=[];chars=0};
 plan.rows.forEach((s,i)=>{if(s.voice_id!==plan.narrator||cached.has(cache.segmentAudioKey(identity(s)))){flush();return}if(chars+s.text.length+1>1800)flush();current.push({index:i,...s});chars+=s.text.length+1});flush();
 progress({phase:'plan',groups:groups.length,missing_rows:groups.reduce((n,g)=>n+g.length,0)});
 let prepared=0;
 for(const group of groups){
  const text=group.map(s=>s.text).join('\n'),hash=require('node:crypto').createHash('sha256').update(text).digest('hex').slice(0,16),dir=path.join(folder,'aligned-'+hash);fs.mkdirSync(dir,{recursive:true});
  fs.writeFileSync(path.join(dir,'group-input.json'),JSON.stringify({text,indices:group.map(s=>s.index),voice_id:plan.narrator}));
  const audio=path.join(dir,'source.mp3'),receipt=path.join(dir,'alignment.json');let alignment;
  if(fs.existsSync(receipt)&&fs.existsSync(audio)){alignment=JSON.parse(fs.readFileSync(receipt,'utf8'))}
  else{
   progress({phase:'generate',group:hash,characters:text.length,rows:group.length});
   const response=await fetch('https://api.elevenlabs.io/v1/text-to-speech/'+plan.narrator+'/with-timestamps?output_format=mp3_44100_128',{method:'POST',headers:{'xi-api-key':keys[0],'Content-Type':'application/json'},body:JSON.stringify({text,model_id:'eleven_multilingual_v2',voice_settings:{stability:.7,similarity_boost:.75,style:.45,speed:Number(p.project_payload.tts_speed)||1,use_speaker_boost:true}}),signal:AbortSignal.timeout(240000)});
   if(!response.ok)throw Error('Aligned TTS failed '+response.status+': '+(await response.text()).slice(0,500));
   const result=await response.json();assert(result.audio_base64&&result.alignment);alignment=result.alignment;
   fs.writeFileSync(audio,Buffer.from(result.audio_base64,'base64'));fs.writeFileSync(receipt,JSON.stringify(alignment));
  }
  assert.equal(alignment.characters.join(''),text,'Provider alignment must match original text exactly');
  const starts=alignment.character_start_times_seconds,ends=alignment.character_end_times_seconds;
  assert.equal(starts.length,Array.from(text).length);assert.equal(starts.length,ends.length);
  const boundaries=[0];let cursor=0;
  for(let j=0;j<group.length-1;j++){cursor+=Array.from(group[j].text).length;const last=ends[cursor-1],next=starts[cursor+1];assert(Number.isFinite(last)&&next>=last-.06);boundaries.push(Math.max(last,(last+next)/2));cursor++}
  boundaries.push(ends.at(-1)+.15);assert(boundaries.every((x,i)=>!i||x>boundaries[i-1]));
  let next=0;await Promise.all(Array.from({length:4},async()=>{while(next<group.length){const j=next++,s=group[j],out=path.join(dir,`row-${s.index}.mp3`);if(!fs.existsSync(out))await run(ffmpeg,['-hide_banner','-loglevel','error','-y','-ss',String(boundaries[j]),'-i',audio,'-t',String(boundaries[j+1]-boundaries[j]),'-ar','44100','-ac','1','-c:a','libmp3lame','-b:a','128k',out],{timeout:30000});await save(s,s.index,out);prepared++}}));
  fs.writeFileSync(path.join(dir,'cuts.json'),JSON.stringify({source_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(audio)).digest('hex'),boundaries,indices:group.map(s=>s.index),timing_source:'provider_original_character_alignment'},null,2));
  progress({phase:'persisted',prepared,total:groups.reduce((n,g)=>n+g.length,0),last_group:hash});
 }
 progress({phase:'completed',prepared});
}
main().catch(e=>{progress({phase:'failed',error:e.message});process.exitCode=1});
