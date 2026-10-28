const fs=require('node:fs'),path=require('node:path'),{execFileSync}=require('node:child_process');
const dotenv=require('../auth-web/node_modules/dotenv');
for(const file of ['auth-web/.env.local','.env'])for(const [key,value]of Object.entries(dotenv.parse(fs.readFileSync(file))))if(!process.env[key])process.env[key]=value;
function request(url,headers={},body){
 const config=Object.entries(headers).map(([k,v])=>`header = "${k}: ${v}"`).join('\n');
 const args=['-sS','--max-time','25','--config','-','-w','\n%{http_code}',url];
 if(body){args.push('-X','POST','--data-binary',JSON.stringify(body));}
 const raw=execFileSync('curl.exe',args,{input:config,encoding:'utf8'}),split=raw.lastIndexOf('\n');
 const text=raw.slice(0,split);let data;try{data=JSON.parse(text)}catch{}
 return {status:Number(raw.slice(split+1)),data};
}
const base=process.env.NEXT_PUBLIC_SUPABASE_URL,key=process.env.SUPABASE_SERVICE_ROLE_KEY;
const profile=request(base+'/rest/v1/profiles?select=pin_code&email=eq.supapitmusic%40gmail.com&limit=1',{apikey:key,Authorization:'Bearer '+key});
if(!profile.data?.[0]?.pin_code)throw Error('No saved PIN available for authorized account check');
const login=request('https://studio.airing.work/api/std/login',{'Content-Type':'application/json'},{email:'supapitmusic@gmail.com',password:profile.data[0].pin_code});
console.log(JSON.stringify({route:'login',status:login.status,error:login.data?.error,success:login.data?.success}));
if(!login.data?.session_token)process.exit(1);
const token=login.data.session_token,pid='05e173f1-46a4-42e6-b543-6d7ba4458368';
for(const suffix of ['me',`projects/${pid}/ae-mouth`,`projects/${pid}/pipeline`,`projects/${pid}/speaker-coordinates`,`projects/${pid}/lipsync`,`projects/${pid}/region-layers`,`projects/${pid}/region-motion`,`projects/${pid}/motion-automation`]){
 if(process.argv.includes('--pipeline-only')&&!suffix.endsWith('/pipeline'))continue;
 const start=Date.now();try{const r=request('https://studio.airing.work/api/std/'+suffix,{Authorization:'Bearer '+token});console.log(JSON.stringify({route:suffix,status:r.status,ms:Date.now()-start,error:r.data?.error}));}catch{console.log(JSON.stringify({route:suffix,error:'timeout/network'}));}
}
