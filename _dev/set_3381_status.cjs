const fs=require('node:fs'),path=require('node:path'),{createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),web=path.join(root,'auth-web'); if(fs.existsSync(path.join(root,'.env'))) process.loadEnvFile(path.join(root,'.env'));
const req=createRequire(path.join(web,'package.json')),ts=req('typescript'),cache=new Map();
function load(name){if(cache.has(name))return cache.get(name);const ex={};cache.set(name,ex);const file=path.join(web,'lib',name+'.ts'),lr=createRequire(file);new Function('exports','require',ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText)(ex,id=>{if(id.startsWith('@/lib/'))return load(id.slice(6));if(id.startsWith('./')&&fs.existsSync(path.join(web,'lib',id+'.ts')))return load(id.slice(2));return lr(id)});return ex}
async function main(){const db=load('supabaseAdmin').supabaseAdmin;const status=process.argv[2];const {error}=await db.from('std_projects').update({status,submitted_at:status==='review_requested'?new Date().toISOString():null,updated_at:new Date().toISOString()}).eq('id','6b46f709-b4bf-4ccd-ac12-9c8c3981e249');if(error)throw error;console.log(status)}
main().catch(e=>{console.error(e);process.exit(1)});

