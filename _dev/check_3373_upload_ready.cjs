const fs=require('node:fs'),rt=require('../scripts/std_web_runtime.cjs'),db=rt.load('supabaseAdmin').supabaseAdmin;
(async()=>{
 const results=await Promise.all([
  db.from('std_projects').select('topic_queue_id,project_payload').eq('id','e9233112-f0d7-4b35-91bf-2f892844eb30').single(),
  db.from('remote_render_queue').select('id,status,metadata,result_file_id').eq('id','3be3a8da-2f9e-4227-828d-8a422f3db748').single(),
  db.from('categories').select('upload_channel_id,upload_channel_name,upload_channel_handle').eq('id',13).single(),
  db.from('global_settings').select('value').eq('key','std_youtube_channel_1').single(),
  rt.load('googleDriveConfig').getGoogleDriveConfig(),
 ]);
 for(const r of results.slice(0,4))if(r.error)throw r.error;
 const p=results[0].data.project_payload,q=results[1].data,channel=JSON.parse(results[3].data.value),oauth=rt.load('stdYoutubeChannelOAuth').readYoutubeCredentials(channel.credentials,results[4].clientSecret);
 const tokenRes=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:oauth.client_id,client_secret:oauth.client_secret,refresh_token:oauth.refresh_token,grant_type:'refresh_token'}),signal:AbortSignal.timeout(20000)});
 const token=await tokenRes.json();if(!tokenRes.ok)throw Error('OAuth refresh '+token.error);
 const channelRes=await fetch('https://www.googleapis.com/youtube/v3/channels?part=snippet,status&mine=true',{headers:{Authorization:'Bearer '+token.access_token},signal:AbortSignal.timeout(20000)});
 const data=await channelRes.json();if(!channelRes.ok)throw Error('Channel lookup HTTP '+channelRes.status);
 const verified=data.items?.find(x=>x.id===channel.youtube_channel_id);
 const config=JSON.parse(fs.readFileSync('output/project-recovery-e9233112/subtitle-only-render-config.json','utf8'));
 const meta=await rt.load('gcsStorage').getGcsObjectMetadata({bucket:q.metadata.gcs_bucket||q.metadata.storage_bucket||'air-studio-prod',objectPath:q.metadata.gcs_path||q.metadata.storage_path});
 const audit={topic:results[0].data.topic_queue_id,render:{status:q.status,resultSaved:!!q.result_file_id,version:config.render_version,storageBytes:meta.size},publish:p.publish_metadata,thumbnailSaved:!!p.thumbnail_design,renderMetadataKeys:Object.keys(q.metadata),category:results[2].data,channel:{authenticated:!!verified,id:verified?.id,title:verified?.snippet.title,handle:verified?.snippet.customUrl,longUploads:verified?.status.longUploadsStatus,uploadScope:oauth.scopes?.includes('https://www.googleapis.com/auth/youtube.upload')},subtitles:config.subtitles.length};
 fs.writeFileSync('output/project-recovery-e9233112/current-upload-readiness.json',JSON.stringify(audit,null,2));console.log(JSON.stringify(audit,null,2));
})().catch(e=>{console.error(e.message);process.exitCode=1});
