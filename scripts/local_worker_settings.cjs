// Loopback-only bridge. Reuses the web validators and handlers without a web deployment.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const {createRequire} = require('node:module');
const root = path.resolve(__dirname, '..'), web = path.join(root, 'auth-web');
const req = createRequire(path.join(web, 'package.json')), ts = req('typescript');
for (const file of [path.join(root,'.env'),path.join(web,'.env.local')]) {
    if (fs.existsSync(file)) for (const [key,value] of Object.entries(req('dotenv').parse(fs.readFileSync(file)))) if (!process.env[key]) process.env[key]=value;
}
function loader(auth) {
    const cache = new Map();
    function load(file) {
        file = path.resolve(file); if (cache.has(file)) return cache.get(file);
        if (file === path.join(web,'lib','stdWeb.ts')) return {requireStdUser: async()=>auth};
        const exports = {}; cache.set(file,exports); const local = createRequire(file);
        const code = ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
        new Function('exports','require',code)(exports, name=>{
            let base = name.startsWith('@/') ? path.join(web,name.slice(2)) : name.startsWith('.') ? path.resolve(path.dirname(file),name) : null;
            if (base) { if (fs.existsSync(base+'.ts')) return load(base+'.ts'); if (fs.existsSync(base+'.json')) return local(base+'.json'); }
            return local(name);
        });
        return exports;
    }
    return load;
}
const editable = p => !p.submitted_at && !['review_requested','approved','canceled'].includes(p.status);
async function main(input, dependencies={}) {
    const method = input.method || 'GET', url = new URL(input.path,'http://127.0.0.1');
    const load = dependencies.load || loader(null), db = dependencies.db || load(path.join(web,'lib/supabaseAdmin.ts')).supabaseAdmin;
    if (url.pathname === '/api/local/projects' && method==='GET') {
        const result = await db.from('std_projects').select('id,title,employee_email,status,submitted_at,updated_at').order('updated_at',{ascending:false}).limit(500);
        if (result.error) throw result.error;
        return {status:200,data:{projects:result.data||[]}};
    }
    const match = url.pathname.match(/^\/api\/(?:local\/projects|std\/projects)\/([a-f0-9-]{36})(?:\/(.*))?$/i);
    const id = match?.[1] || input.project_id;
    if (!/^[a-f0-9-]{36}$/i.test(id||'')) return {status:400,data:{error:'프로젝트를 먼저 선택하세요.'}};
    const row = await db.from('std_projects').select('*').eq('id',id).maybeSingle();
    if (row.error) throw row.error;
    if (!row.data) return {status:404,data:{error:'프로젝트를 찾을 수 없습니다.'}};
    const project = row.data;
    // The provider vault remains server-side. The native UI talks to the fixed
    // settings API; neither its encryption key nor provider secrets are copied.
    if(url.pathname==='/api/local/account-login' && method==='POST') {
        const response=await fetch('https://studio.airing.work/api/std/login',{method:'POST',redirect:'error',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:project.employee_email,password:String(input.body?.password||'')}),signal:AbortSignal.timeout(45000)});
        const data=await response.json();
        if(!response.ok||!data.session_token)return {status:response.status,data:{error:data.error||'계정 연결에 실패했습니다.'}};
        return {status:200,session_token:data.session_token,data:{connected:true,email:project.employee_email}};
    }
    if(url.pathname==='/api/std/video-models' || (match?.[2]==='web-motion'&&url.pathname.startsWith('/api/std/projects/'))) {
        if(!['GET','POST'].includes(method))return {status:405,data:{error:'지원하지 않는 요청입니다.'}};
        const session=input.session_token||load(path.join(web,'lib/desktopSession.ts')).signDesktopSessionToken(project.employee_email);
        const response=await fetch('https://studio.airing.work'+url.pathname,{method,redirect:'error',headers:{Authorization:'Bearer '+session,'Content-Type':'application/json'},...(method==='POST'?{body:JSON.stringify(input.body||{})}:{}),signal:AbortSignal.timeout(90000)});
        const data=await response.json();
        return {status:response.status,data:response.status===401?{error:'기존 영상 API 설정 계정 연결을 열어 이 워커에서 로그인한 뒤 다시 불러오세요.',account_connection_required:true}:data};
    }
    if (url.pathname===`/api/local/projects/${id}` && method==='GET') {
        const scenes=await db.from('std_project_scenes').select('*').eq('project_id',id).order('scene_number');
        if(scenes.error)throw scenes.error;
        return {status:200,data:{project:{id,title:project.title,employee_email:project.employee_email,status:project.status,submitted_at:project.submitted_at,updated_at:project.updated_at,render_settings:project.project_payload?.render_settings||{},subtitles:project.project_payload?.subtitles||[]},scenes:scenes.data||[],editable:editable(project)}};
    }
    if(url.pathname===`/api/local/projects/${id}/settings` && method==='POST') {
        if(!editable(project))return {status:409,data:{error:'제출된 프로젝트는 제작 설정을 변경할 수 없습니다.'}};
        const body=input.body||{};
        if(!body.version||body.version!==project.updated_at)return {status:409,data:{error:'프로젝트가 변경되었습니다. 다시 불러온 뒤 저장하세요.'}};
        const settings={...(project.project_payload?.render_settings||{})};
        if(body.motion!==undefined)settings.motion=load(path.join(web,'lib/stdMotionStudio.ts')).normalizeMotionDraft(body.motion);
        if(body.comic!==undefined)settings.comic=load(path.join(web,'lib/stdComic.ts')).normalizeComicSettings(body.comic);
        if(body.motion===undefined&&body.comic===undefined)return {status:400,data:{error:'저장할 제작 설정이 없습니다.'}};
        const saved=await db.from('std_projects').update({project_payload:{...project.project_payload,render_settings:settings},updated_at:new Date().toISOString()}).eq('id',id).eq('updated_at',body.version).is('submitted_at',null).eq('status',project.status).select('updated_at').maybeSingle();
        if(saved.error)throw saved.error;
        if(!saved.data)return {status:409,data:{error:'다른 작업에서 프로젝트를 변경했습니다. 다시 불러오세요.'}};
        return {status:200,data:{updated_at:saved.data.updated_at,render_settings:settings}};
    }
    let route;
    const allowed = { 'ae-scene':['GET','POST'],motion:['GET','POST'],'motion-automation':['GET'],'web-motion':['GET','POST'],'assets/init':['POST'],'assets/complete':['POST'],'assets/file':['GET'] };
    if(match && url.pathname.startsWith('/api/std/projects/') && allowed[match[2]]?.includes(method)) route=`app/api/std/projects/[projectId]/${match[2]}/route.ts`;
    if(url.pathname==='/api/std/video-models' && ['GET','POST'].includes(method))route='app/api/std/video-models/route.ts';
    if(url.pathname==='/api/std/assets/gcs-file'&&method==='GET')route='app/api/std/assets/gcs-file/route.ts';
    if(!route)return {status:404,data:{error:'지원하지 않는 로컬 제작 요청입니다.'}};
    const profile=await db.from('profiles').select('id,email').eq('email',project.employee_email).maybeSingle();
    if(profile.error)throw profile.error;
    const auth={ok:true,requester:{email:project.employee_email,user:{id:profile.data?.id||'local-media-worker',email:project.employee_email},profile:profile.data||{email:project.employee_email}}};
    const handler=loader(auth)(path.join(web,route));
    const headers={'Content-Type':'application/json',...(input.range?{Range:input.range}:{})};
    const request=new Request(url,{method,headers,...(method==='POST'?{body:JSON.stringify(input.body||{})}:{})});
    const response=await handler[method](request,{params:{projectId:id}});
    const contentType=response.headers.get('content-type')||'';
    if(contentType.includes('json'))return {status:response.status,data:await response.json()};
    if(response.headers.get('location'))return {status:response.status,redirect:response.headers.get('location')};
    const spool=path.join(root,'output/local-worker-api');fs.mkdirSync(spool,{recursive:true});
    const file=path.join(spool,crypto.randomUUID()+'.media');
    const {pipeline}=require('node:stream/promises'),{Readable}=require('node:stream');
    try {await pipeline(Readable.fromWeb(response.body),fs.createWriteStream(file));}
    catch(error){fs.rmSync(file,{force:true});throw error;}
    return {status:response.status,file,headers:Object.fromEntries(['content-type','content-length','content-range','accept-ranges'].flatMap(k=>response.headers.has(k)?[[k,response.headers.get(k)]]:[]))};
}
module.exports={main,loader,editable};
if(require.main===module){let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>input+=s);process.stdin.on('end',async()=>{try{const result=await main(JSON.parse(input));console.log('AIR_RESULT:'+JSON.stringify(result));}catch(error){console.log('AIR_RESULT:'+JSON.stringify({status:400,data:{error:error.message||'제작 설정 처리 실패'}}));}});}
