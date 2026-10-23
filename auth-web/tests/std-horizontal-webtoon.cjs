const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),path=require('node:path');
const ex={};new Function('exports','require',ts.transpileModule(fs.readFileSync(path.join(__dirname,'../lib/stdHorizontalWebtoon.ts'),'utf8'),{compilerOptions:{module:1,target:9}}).outputText)(ex,id=>({
 './stdMotionStudio':{motionForProject:p=>p.project_payload.render_settings.motion,motionProductionMethod:()=> 'ae'},
 './stdContentIdentity':{selectNarrationAsset:(_,assets)=>assets.find(a=>a.asset_type==='audio')},
 './stdLipSync':{lipSyncPlan:()=>{},lipSyncSceneStarts:()=>[0]},
 './stdSceneMedia':{storageSourceForAsset:a=>a.metadata?.gcs_path},
}[id]||require(id)));
const panel=()=>({crop:[0,0,1,1],frame:[0,0,1,1],reveal:0,zoom_from:1,zoom_to:1.05});
const plan=()=>({version:1,evidence:['Full face and speech balloon visible'],shots:[{start:0,end:1,panels:[panel()]}]});
test('safe full panel and nonoverlapping side-by-side layouts validate',()=>{
 assert.equal(ex.validateWebtoonPlan(plan()).shots.length,1);
 const p=plan();p.shots[0].panels=[{...panel(),frame:[0,0,.5,1]},{...panel(),frame:[.5,0,.5,1],reveal:.3}];assert.equal(ex.validateWebtoonPlan(p).shots[0].panels.length,2);
});
test('gaps, cropped outside artwork, blank starts, excessive zoom and overlap fail',()=>{
 for(const mutate of [p=>p.shots[0].start=.1,p=>p.shots[0].end=.9,p=>p.shots[0].panels[0].crop=[.9,0,.2,1],p=>p.shots[0].panels[0].reveal=.2,p=>p.shots[0].panels[0].zoom_to=2,p=>p.shots[0].panels.push(panel())]){const p=plan();mutate(p);assert.throws(()=>ex.validateWebtoonPlan(p));}
});
test('changing source or final voice invalidates prepared direction; image precedes incidental video',()=>{
 const project={project_payload:{render_settings:{motion:{enabled:true,edit_mode:'horizontal_webtoon',aspect:'16:9',fps:24}},subtitles:[{scene_number:1}]}},scenes=[{scene_number:1}];
 const assets=[{id:'voice',asset_type:'audio',metadata:{subtitle_timeline:[{text:'line',start:0,end:5}]}},{id:'image',asset_type:'image',scene_number:1,status:'uploaded',metadata:{gcs_path:'image.png'}},{id:'clip',asset_type:'video',scene_number:1,status:'uploaded',metadata:{gcs_path:'clip.mp4'}}];
 const first=ex.webtoonInputs(project,scenes,assets)[0];assert.equal(first.asset.id,'image');
 const job={id:'job',metadata:{kind:'motion_preview',state:'ready',fingerprint:first.fingerprint,source_sha256:'a'.repeat(64),suggestion:{webtoon:plan()}}};
 assert.equal(ex.readyWebtoonPlan(first,[job]).job_id,'job');
 assets[0].metadata.subtitle_timeline[0].text='changed';const changed=ex.webtoonInputs(project,scenes,assets)[0];assert.notEqual(changed.fingerprint,first.fingerprint);assert.throws(()=>ex.readyWebtoonPlan(changed,[job]));
 assets[1].metadata.gcs_path='replacement.png';assert.notEqual(ex.webtoonInputs(project,scenes,assets)[0].fingerprint,changed.fingerprint);
});
