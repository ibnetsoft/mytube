"""Read-back verification using the actual web API's media hydration functions.

This is not an authenticated browser UI test. No remote writes.
"""
import hashlib
import json
import subprocess
from scripts.audit_active_content import fetch
from scripts.repair_active_materials import dump
from scripts.publish_3197_approved_visuals import OUT, PID, ROOT, SHA

p=fetch('std_projects',id='eq.'+PID)[0]
scenes=fetch('std_project_scenes',project_id='eq.'+PID,order='scene_number.asc')
assets=fetch('std_project_assets',project_id='eq.'+PID,status='in.(uploaded,assigned)',order='id.asc')
topic=fetch('topics_queue',id='eq.3197')[0]
uploaded=json.loads((OUT/'uploaded.json').read_text(encoding='utf-8'))
assert hashlib.sha256(p['project_payload']['script'].encode()).hexdigest()==SHA
js=r"""
const fs=require('fs'),ts=require('./auth-web/node_modules/typescript');
const src=fs.readFileSync('./auth-web/app/api/std/projects/[projectId]/route.ts','utf8');
const pure=src.slice(src.indexOf('const CONTENT_ASSETS_BUCKET'),src.indexOf('function payloadScenes'));
const supabaseAdmin={storage:{from:bucket=>({getPublicUrl:path=>({data:{publicUrl:`https://giorysjpgxzdypbmxwmx.supabase.co/storage/v1/object/public/${bucket}/${path}`}})})}};
const hydrate=new Function('supabaseAdmin',ts.transpileModule(pure,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText+';return hydrateSceneMedia;')(supabaseAdmin);
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const source=new Map();
for(const s of input.project.source_payload.pregenerated_structure.scenes)source.set(s.scene_number||s.scene_order,s);
for(const [i,s] of input.topic.pregenerated_structure.scenes.entries())source.set(s.scene_number||s.scene_order||i+1,s);
process.stdout.write(JSON.stringify(input.scenes.map(s=>hydrate(s,input.assets,source.get(s.scene_number)))));
"""
hydrated=json.loads(subprocess.check_output(['node','-e',js],cwd=ROOT,input=json.dumps({
    'project':p,'scenes':scenes,'assets':assets,'topic':topic}).encode()))
assert len(hydrated)==53
for i,s in enumerate(hydrated,1):
    assert s['scene_number']==i
    assert s['image_url']==uploaded[f'scenes/scene-{i:03d}.png']['url']
    assert not s.get('video_url')
for sub in p['project_payload']['subtitles']:
    assert sub['image_url']==uploaded[f"scenes/scene-{sub['scene_number']:03d}.png"]['url']
    assert not sub.get('video_url')
result={'project_id':PID,'api_hydrated_images':53,'subtitle_blocks':len(p['project_payload']['subtitles']),
    'stale_video_references':0,'script_unchanged':True,'browser_ui_verified':False,
    'browser_note':'Verification tab requires login; existing Chrome tab connection timed out.'}
dump(OUT/'web-mapping-verified.json',result)
print(json.dumps(result))
