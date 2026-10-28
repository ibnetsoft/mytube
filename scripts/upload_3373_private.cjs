const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const rt=require('./std_web_runtime.cjs'),db=rt.load('supabaseAdmin').supabaseAdmin;
const dir=path.resolve('output/project-recovery-e9233112'),receiptFile=path.join(dir,'youtube-private-upload.json');
const video=path.resolve('output/final-renders/e9233112-v9-restored-subtitles.mp4'),thumbnail=path.resolve('output/thumbnail-3373-scene51-upload.jpg');
const projectId='e9233112-f0d7-4b35-91bf-2f892844eb30',queueId='3be3a8da-2f9e-4227-828d-8a422f3db748',channelId='UC3KbFJTqYtoautDGWlL21lg';
let receipt=fs.existsSync(receiptFile)?JSON.parse(fs.readFileSync(receiptFile,'utf8')):{};
function save(values){receipt={...receipt,...values,updated_at:new Date().toISOString()};fs.writeFileSync(receiptFile,JSON.stringify(receipt,null,2));}
async function error(response){const body=await response.json().catch(()=>({}));throw Error('YouTube HTTP '+response.status+' '+(body.error?.errors?.[0]?.reason||body.error?.message||''));}
(async()=>{
 const [pr,ch,gconfig,qr]=await Promise.all([db.from('std_projects').select('project_payload').eq('id',projectId).single(),db.from('global_settings').select('value').eq('key','std_youtube_channel_1').single(),rt.load('googleDriveConfig').getGoogleDriveConfig(),db.from('remote_render_queue').select('metadata,status').eq('id',queueId).single()]);
 for(const r of [pr,ch,qr])if(r.error)throw r.error;
 if(qr.data.status!=='completed')throw Error('Final render incomplete');
 const stored=JSON.parse(ch.data.value),oauth=rt.load('stdYoutubeChannelOAuth').readYoutubeCredentials(stored.credentials,gconfig.clientSecret);
 if(stored.youtube_channel_id!==channelId)throw Error('Saved channel differs');
 let access;
 async function refresh(){const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:oauth.client_id,client_secret:oauth.client_secret,refresh_token:oauth.refresh_token,grant_type:'refresh_token'}),signal:AbortSignal.timeout(30000)});if(!r.ok)await error(r);access=(await r.json()).access_token;}
 await refresh();
 const auth=()=>({Authorization:'Bearer '+access});
 const channelResponse=await fetch('https://www.googleapis.com/youtube/v3/channels?part=snippet,status&mine=true',{headers:auth(),signal:AbortSignal.timeout(30000)});if(!channelResponse.ok)await error(channelResponse);
 const actual=(await channelResponse.json()).items?.find(x=>x.id===channelId);if(!actual||actual.status.longUploadsStatus!=='allowed')throw Error('Requested channel or long upload permission missing');
 console.log(JSON.stringify({channel:actual.snippet.title,channelId,privacy:'private',renderVersion:9}));
 const publish=pr.data.project_payload.publish_metadata,size=fs.statSync(video).size;
 if(size!==641495698)throw Error('Final video differs from completed render');
 const body={snippet:{title:publish.title,description:publish.description,tags:publish.tags,categoryId:'24',defaultLanguage:'ja',defaultAudioLanguage:'ja'},status:{privacyStatus:'private',selfDeclaredMadeForKids:false}};
 if(receipt.channel_id&&receipt.channel_id!==channelId)throw Error('Upload receipt channel differs');
 if(qr.data.metadata.youtube_video_id&&!receipt.video_id)throw Error('Existing uploaded video must be reconciled before a new upload');
 if(!receipt.video_id){
  if(!receipt.session){
   const response=await fetch('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',{method:'POST',headers:{...auth(),'Content-Type':'application/json; charset=UTF-8','X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':String(size)},body:JSON.stringify(body),signal:AbortSignal.timeout(30000)});if(!response.ok)await error(response);
   const session=response.headers.get('location');if(!session)throw Error('Upload session missing');save({session,channel_id:channelId,channel_name:actual.snippet.title,render_queue_id:queueId,size,metadata:body,thumbnail_path:thumbnail});
  }
  const fd=fs.openSync(video,'r');
  for(let retry=0;retry<8&&!receipt.video_id;retry++){
   try{
    const check=await fetch(receipt.session,{method:'PUT',headers:{...auth(),'Content-Length':'0','Content-Range':`bytes */${size}`},body:Buffer.alloc(0),signal:AbortSignal.timeout(30000)});
    if(check.ok){const result=await check.json();save({video_id:result.id,video_status:result.status});break;}
    if(check.status!==308)await error(check);
    let offset=check.headers.get('range')?Number(check.headers.get('range').split('-').at(-1))+1:0;
    while(offset<size){
     const length=Math.min(8*1024*1024,size-offset),buffer=Buffer.alloc(length);fs.readSync(fd,buffer,0,length,offset);
     const response=await fetch(receipt.session,{method:'PUT',headers:{...auth(),'Content-Type':'video/mp4','Content-Length':String(length),'Content-Range':`bytes ${offset}-${offset+length-1}/${size}`},body:buffer,signal:AbortSignal.timeout(120000)});
     if(response.ok){const result=await response.json();save({video_id:result.id,video_status:result.status,uploaded_at:new Date().toISOString()});break;}
     if(response.status!==308)await error(response);
     offset=Number(response.headers.get('range').split('-').at(-1))+1;const progress=Math.round(offset/size*100);save({progress});console.log('Video upload',progress+'%');
    }
   }catch(e){console.log('Resuming upload',retry+1,e.message);if(retry===7||e.message.includes('YouTube HTTP 4'))throw e;await refresh();await new Promise(r=>setTimeout(r,Math.min(2**retry*1000,30000)));}
  }
  fs.closeSync(fd);
 }
 if(!receipt.video_id)throw Error('Video ID not received');
 if(!receipt.thumbnail_set){
  const response=await fetch('https://www.googleapis.com/upload/youtube/v3/thumbnails/set?uploadType=media&videoId='+encodeURIComponent(receipt.video_id),{method:'POST',headers:{...auth(),'Content-Type':'image/jpeg'},body:fs.readFileSync(thumbnail),signal:AbortSignal.timeout(60000)});if(!response.ok)await error(response);await response.json();save({thumbnail_set:true,thumbnail_sha256:crypto.createHash('sha256').update(fs.readFileSync(thumbnail)).digest('hex')});console.log('Scene 51 thumbnail applied');
 }
 const verify=await fetch('https://www.googleapis.com/youtube/v3/videos?part=snippet,status,processingDetails&id='+encodeURIComponent(receipt.video_id),{headers:auth(),signal:AbortSignal.timeout(30000)});if(!verify.ok)await error(verify);
 const uploaded=(await verify.json()).items?.[0];if(uploaded?.snippet.channelId!==channelId||uploaded?.status.privacyStatus!=='private')throw Error('Uploaded video channel/privacy mismatch');
 save({verified_private:true,title:uploaded.snippet.title,processing_status:uploaded.processingDetails?.processingStatus,url:'https://www.youtube.com/watch?v='+receipt.video_id});
 const latest=await db.from('remote_render_queue').select('metadata').eq('id',queueId).single();if(latest.error)throw latest.error;
 const updated=await db.from('remote_render_queue').update({metadata:{...latest.data.metadata,youtube_video_id:receipt.video_id,youtube_url:receipt.url,youtube_privacy_status:'private',youtube_thumbnail_source:'scene51-generated',youtube_uploaded_at:receipt.uploaded_at,admin_publish_status:'uploaded_private',admin_action_required:null},updated_at:new Date().toISOString()}).eq('id',queueId);if(updated.error)throw updated.error;
 console.log(JSON.stringify({completed:true,videoId:receipt.video_id,url:receipt.url,privacy:'private',thumbnail:true,processing:receipt.processing_status}));
})().catch(e=>{console.error(e.message);save({last_error:e.message});process.exitCode=1});
