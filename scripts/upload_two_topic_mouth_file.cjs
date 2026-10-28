const fs=require('node:fs'),crypto=require('node:crypto');
const rt=require('./std_web_runtime.cjs'),g=rt.load('gcsStorage');
(async()=>{const [file,objectPath,mime]=process.argv.slice(2);
 if(!/^topics\/(3376|3377)\/mouth-(layers|previews)\//.test(objectPath))throw Error('Unexpected mouth delivery path');
 const buffer=fs.readFileSync(file),result=await g.uploadGcsBuffer({objectPath,data:buffer,contentType:mime});
 const metadata=await g.getGcsObjectMetadata({bucket:result.bucket,objectPath});
 if(metadata.size!==buffer.length)throw Error('Uploaded size differs');
 console.log(JSON.stringify({bucket:result.bucket,path:result.path,url:`/api/std/assets/gcs-file?bucket=${encodeURIComponent(result.bucket)}&path=${encodeURIComponent(result.path)}`,sha256:crypto.createHash('sha256').update(buffer).digest('hex'),size:buffer.length}));
})().catch(e=>{console.error(e.message);process.exitCode=1});
