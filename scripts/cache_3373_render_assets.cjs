const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const gcs=require('./std_web_runtime.cjs').load('gcsStorage');
const config=JSON.parse(fs.readFileSync('output/project-recovery-e9233112/subtitle-only-render-config.json','utf8'));
const root=path.join(os.homedir(),'.air-studio','media-cache');
const destination=path.join(os.tmpdir(),'air-render-checkpoints','3be3a8da-2f9e-4227-828d-8a422f3db748');
const receipts={};
const pending=config.asset_manifest.files.filter(f=>{
 const sha=f.content_identity?.source_sha256||f.sha256;
 const target=path.join(destination,f.path);
 if(fs.existsSync(target)){const data=fs.readFileSync(target);const actual=crypto.createHash('sha256').update(data).digest('hex');if(!sha||actual===sha){receipts[f.path]=actual;return false;}}
 const key=crypto.createHash('sha256').update(JSON.stringify([f.gcs_bucket,f.gcs_path,sha]).replaceAll(',',', ')).digest('hex');
 f.cacheDir=path.join(root,key);f.expectedSha=sha;return true;
});
(async()=>{
 await gcs.getGcsConfig();console.log('Missing cached assets:',pending.length);
 let next=0,done=0;
 await Promise.all(Array.from({length:4},async()=>{
  while(next<pending.length){const f=pending[next++];
   const data=(await gcs.downloadGcsObjectViaSignedUrl({bucket:f.gcs_bucket,objectPath:f.gcs_path})).buffer;
   const sha=crypto.createHash('sha256').update(data).digest('hex');if(f.expectedSha&&sha!==f.expectedSha)throw Error('Source hash mismatch '+f.path);
   const target=path.join(destination,f.path);fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target+'.seed',data);fs.renameSync(target+'.seed',target);receipts[f.path]=sha;
   fs.mkdirSync(f.cacheDir,{recursive:true});fs.writeFileSync(path.join(f.cacheDir,'node-seed.tmp'),data);
   fs.writeFileSync(path.join(f.cacheDir,'receipt.json'),JSON.stringify({sha256:sha,generation:'local_exact_hash'}));
   fs.renameSync(path.join(f.cacheDir,'node-seed.tmp'),path.join(f.cacheDir,'data'));
   console.log('Cached',++done,'/',pending.length,f.path);
  }
 }));
 fs.writeFileSync(path.join(destination,'signed-local-receipts.json'),JSON.stringify(receipts));
})().catch(e=>{console.error(e.message);process.exitCode=1});
