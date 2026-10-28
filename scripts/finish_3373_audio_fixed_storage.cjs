const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const file=path.resolve('output/project-recovery-e9233112/audio-fixed-v11/output.mp4');
const saved=JSON.parse(fs.readFileSync(file+'.gcs-upload.json','utf8'));
(async()=>{
 const fd=fs.openSync(file,'r');let offset=0;
 for(let retry=0;retry<6;retry++){
  try{
   const status=await fetch(saved.session,{method:'PUT',headers:{'Content-Length':'0','Content-Range':`bytes */${saved.size}`},body:Buffer.alloc(0),signal:AbortSignal.timeout(30000)});
   if(status.ok){fs.writeFileSync('output/project-recovery-e9233112/audio-fixed-storage.json',JSON.stringify({bucket:saved.bucket,path:saved.path,url:'/api/std/assets/gcs-file?bucket='+encodeURIComponent(saved.bucket)+'&path='+encodeURIComponent(saved.path),bytes:saved.size}));console.log('Storage upload completed');return;}
   if(status.status!==308)throw Error('Upload session status '+status.status);
   offset=status.headers.get('range')?Number(status.headers.get('range').split('-').at(-1))+1:0;
   while(offset<saved.size){
    const length=Math.min(8*1024*1024,saved.size-offset),data=Buffer.alloc(length);fs.readSync(fd,data,0,length,offset);
    const response=await fetch(saved.session,{method:'PUT',headers:{'Content-Type':'video/mp4','Content-Length':String(length),'Content-Range':`bytes ${offset}-${offset+length-1}/${saved.size}`},body:data,signal:AbortSignal.timeout(120000)});
    if(response.ok){fs.writeFileSync('output/project-recovery-e9233112/audio-fixed-storage.json',JSON.stringify({bucket:saved.bucket,path:saved.path,url:'/api/std/assets/gcs-file?bucket='+encodeURIComponent(saved.bucket)+'&path='+encodeURIComponent(saved.path),bytes:saved.size}));console.log('Storage upload completed');return;}
    if(response.status!==308)throw Error('Upload response '+response.status);
    offset=Number(response.headers.get('range').split('-').at(-1))+1;
    console.log('Saved',Math.round(offset/saved.size*100)+'%');
   }
  }catch(e){console.log('Storage transport retry',retry+1,e.name);if(retry===5)throw e;}
 }
})().catch(e=>{console.error(e.name);process.exitCode=1});
