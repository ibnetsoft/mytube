const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{execFileSync}=require('node:child_process'),ts=require('typescript'),sharp=require('sharp'),ffmpeg=require('ffmpeg-static');
function load(file,mocks={}) {
 const ex={};const filename=path.resolve(__dirname,'../',file), req=require('node:module').createRequire(filename);
 new Function('exports','require',ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:1,target:9,esModuleInterop:true}}).outputText)(ex,n=>mocks[n]||(n.startsWith('./')?load('lib/'+n.slice(2)+'.ts',mocks):req(n)));return ex;
}
const geometry=load('lib/stdSpeakerGeometry.ts');
const video={id:'video12',asset_type:'video',scene_number:12,status:'uploaded',metadata:{gcs_bucket:'source',gcs_path:'original.mp4'}};
const project={project_payload:{subtitles:[{scene_number:12,dialogue_kind:'dialogue',dialogue_speaker:'Father',text:'Hello'}]}};
test('video-only scene uses its matching stored frame and invalidates replaced clips',()=>{
 const ref={id:'ref12',asset_type:'other',scene_number:12,status:'uploaded',metadata:{kind:'speaker_video_reference',source_video_id:video.id,source_video_path:'original.mp4',gcs_path:'ref.png'}};
 assert.equal(geometry.coordinateScenes(project,[video])[0].image,null);
 assert.equal(geometry.coordinateScenes(project,[video])[0].video.id,video.id);
 assert.equal(geometry.coordinateScenes(project,[ref,video])[0].image.id,'ref12');
 assert.equal(geometry.coordinateScenes(project,[ref,{...video,id:'replacement'}])[0].image,null);
 assert.equal(geometry.coordinateScenes(project,[ref,{...video,metadata:{...video.metadata,gcs_path:'new.mp4'}}])[0].image,null);
});
test('actual FFmpeg frame is persisted separately and reused for the same video',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'air-frame-test-'));
 try {
  const filename=path.join(dir,'test.mp4');execFileSync(ffmpeg,['-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=red:s=160x90:d=1','-c:v','libx264',filename]);
  const bytes=fs.readFileSync(filename);let uploaded,insertion,downloads=0;
  const library=load('lib/stdSpeakerVideoFrame.ts',{'./stdSpeakerGeometry':geometry,'./gcsStorage':{
   downloadGcsObject:async ref=>{downloads++;assert.equal(ref.objectPath,'original.mp4');return bytes},
   uploadGcsBuffer:async input=>{uploaded=input;return{bucket:'references',path:input.objectPath}}
  }});
  const db={from:()=>({insert:row=>{insertion=row;return{select:()=>({single:async()=>({data:{...row,id:'reference'}})})}}})};
  const scene=geometry.coordinateScenes(project,[video])[0];
  const result=await library.prepareSpeakerVideoFrame(db,'project',scene,[video]);
  assert.equal(insertion.asset_type,'other');assert.equal(insertion.metadata.source_video_id,video.id);
  assert.equal(insertion.metadata.frame_seconds,0);assert.equal(insertion.metadata.source_video_sha256.length,64);
  assert.equal((await sharp(uploaded.data).metadata()).width,160);
  assert.equal((await sharp(uploaded.data).metadata()).height,90);
  const again=await library.prepareSpeakerVideoFrame(db,'project',scene,[result,video]);
  assert.equal(again.id,result.id);assert.equal(downloads,1);
 } finally {fs.rmSync(dir,{recursive:true,force:true})}
});
