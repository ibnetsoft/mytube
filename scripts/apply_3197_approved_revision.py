"""Apply the exact user-approved 53-scene draft to ONE unsubmitted project.

Dry-run by default. Backups, optimistic concurrency and rollback preserve user work.
No topic-wide propagation, image generation, Drive changes, or invented QA scores.
"""
import copy
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_active_content import fetch
from scripts.repair_active_materials import patch_row, dump

PID = '10b3d223-1457-415a-ba40-7b947c6c1b3d'
DRAFT = ROOT / 'docs/script-revisions/3197-approved-20260912.md'
TEXT_KEYS = ('text', 'scene_text', 'narration', 'narration_text', 'script_excerpt', 'scene_summary', 'scene_situation')
# Context-read speaker assignments for this approved draft, NOT a heuristic dialogue classifier.
SPEAKERS = {8:['시어머니'],10:['순임'],20:['덕수'],22:['시어머니'],31:['장 노인'],
    33:['덕수','순임'],34:['시어머니','순임'],42:['순임'],46:['덕수'],49:['순임','덕수']}

def text_scene(scene, text):
    result = copy.deepcopy(scene)
    for key in TEXT_KEYS:
        if key in result or key in ('scene_text', 'narration', 'script_excerpt'):
            result[key] = text
    return result

def update_structure(value, sections, annotations, revision):
    result = copy.deepcopy(value or {})
    scenes = result.get('scenes') or []
    if len(scenes) != 53:
        raise RuntimeError('Expected existing 53-scene structure')
    result['scenes'] = [text_scene(s, sections[i]) for i,s in enumerate(scenes)]
    # Old narrative plans/reviews are not evidence about the rewritten text.
    for key in ('dialogue_annotations','listener_quality_report','script_quality_report','narrative_blueprint','story_core'):
        result.pop(key, None)
    result.update(dialogue_annotations=annotations, approved_script_revision=revision)
    return result

def main():
    parts = re.split(r'^## (\d+)\s*$', DRAFT.read_text(encoding='utf-8'), flags=re.M)
    assert [int(parts[i]) for i in range(1,len(parts),2)] == list(range(1,54))
    sections = [parts[i].strip() for i in range(2,len(parts),2)]
    script = '\n\n'.join(sections)
    digest = hashlib.sha256(script.encode()).hexdigest()
    p = fetch('std_projects', id='eq.'+PID)[0]
    assert p['employee_email'] == 'supapitmusic@gmail.com'
    assert p['status'] in ('claimed','in_progress') and not p.get('submitted_at')
    if (p.get('project_payload') or {}).get('script') == script:
        print('Already applied; no changes'); return
    scenes = fetch('std_project_scenes',project_id='eq.'+PID,order='scene_number.asc')
    assets = fetch('std_project_assets',project_id='eq.'+PID)
    assert [s['scene_number'] for s in scenes] == list(range(1,54))
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    revision = {'id':'3197-user-approved-20260912','approved_at':now,'source':'conversation_user_approval',
        'script_sha256':digest,'scene_count':53,'independent_listener_review':'not_run',
        'requires_revalidation':['scene_images','video_prompts_1_to_12','uploaded_video_clips','character_references','publish_metadata','thumbnail','tts'],
        'note':'User-approved narrative revision. Existing visual files preserved, not validated against this script.'}
    annotations = {'version':1,'source':'codex-ai','offset_unit':'unicode_codepoints','scenes':[]}
    for number,text in enumerate(sections,1):
        spans=[]
        matches=list(re.finditer('“([^”]+)”',text))
        assert len(matches)==len(SPEAKERS.get(number,[])), number
        for match,speaker in zip(matches,SPEAKERS.get(number,[])):
            spans.append({'start':match.start(1),'end':match.end(1),'text':match.group(1),
                'speaker':speaker,'status':'confirmed','reason':'Direct speech identified from the approved scene context.'})
        annotations['scenes'].append({'scene_number':number,'source_text':text,
            'source_sha256':hashlib.sha256(text.encode()).hexdigest(),'spans':spans})
    editor=copy.deepcopy(p['project_payload']); source=copy.deepcopy(p['source_payload']); progress=copy.deepcopy(p['progress_payload'])
    for target in (editor,source,progress):
        for key in ('script_quality_report','listener_quality_report','narrative_blueprint'):
            target.pop(key,None)
        target['approved_script_revision']=revision
    structure=update_structure(editor.get('structure') or source.get('pregenerated_structure'),sections,annotations,revision)
    editor.update(script=script,pregenerated_script=script,original_worker_script=script,structure=structure,
        subtitles=[],subtitles_completed=False,subtitles_saved=False,has_tts_audio=False,tts_completed=False,
        voice_segments=[],script_repair_profile='user_approved_narrative_revision_v1')
    if isinstance(editor.get('scenes'),list):
        assert len(editor['scenes'])==53
        editor['scenes']=[text_scene(s,sections[i]) for i,s in enumerate(editor['scenes'])]
    source.update(pregenerated_script=script,pregenerated_structure=structure)
    for target in (editor,progress):
        for key in list(target):
            if key in ('audio_url','tts_url','tts_asset_id','tts_drive_file_id','tts_file_name','voice_segments'):
                target.pop(key,None)
        target.update(has_tts_audio=False,tts_completed=False,subtitles_completed=False,subtitles_saved=False,
            script_changed_requires_audio_regeneration=True)
    out=ROOT/'output'/'approved-script-revisions'/str(time.time_ns())
    dump(out/'before.json',{'project':p,'scenes':scenes,'assets':assets})
    updated_scenes=[]
    for index,scene in enumerate(scenes):
        metadata=text_scene(scene.get('metadata') or {},sections[index])
        metadata['approved_script_revision']=revision
        updated_scenes.append({**scene,'scene_text':sections[index],'metadata':metadata})
    # Use the application's exact scene-boundary subtitle splitter, then AI speech spans.
    js=r"""
const fs=require('fs'),ts=require('./auth-web/node_modules/typescript');
function load(p){const e={};new Function('exports',ts.transpileModule(fs.readFileSync(p,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText)(e);return e;}
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const subs=load('auth-web/lib/stdSubtitles.ts').generateSynchronizedSubtitles(input.script,input.scenes,20);
const result=load('auth-web/lib/stdDialogueAnnotations.ts').splitSubtitleDialogueBlocks(subs,input.annotations);
process.stdout.write(JSON.stringify(result));
"""
    subs=json.loads(subprocess.check_output(['node','-e',js],cwd=ROOT,input=json.dumps({'script':script,
        'scenes':[{**s['metadata'],**s,'text':sections[i]} for i,s in enumerate(updated_scenes)],'annotations':annotations}).encode()))
    compact=lambda t:re.sub(r'[\s“”\"‘’\u0027]','',t)
    for i,text in enumerate(sections,1):
        assert compact(''.join(s['text'] for s in subs if s['scene_number']==i))==compact(text), i
    assert set(s['scene_number'] for s in subs)==set(range(1,54))
    editor['subtitles']=subs
    operations=[('std_project_scenes',old,{'scene_text':new['scene_text'],'metadata':new['metadata']}) for old,new in zip(scenes,updated_scenes)]
    # Preserve old audio files, but retire their active association with this revised narration.
    for asset in assets:
        if asset['asset_type']=='audio' and asset['status'] in ('uploaded','assigned'):
            operations.append(('std_project_assets',asset,{'status':'replaced','metadata':{**(asset.get('metadata') or {}),'superseded_by_script_revision':revision['id']}}))
    operations.append(('std_projects',p,{'project_payload':editor,'source_payload':source,'progress_payload':progress}))
    dump(out/'plan.json',{'revision':revision,'operations':[{'table':t,'id':b['id'],'changes':c} for t,b,c in operations]})
    print(json.dumps({'mode':'apply' if '--apply' in sys.argv else 'dry_run','backup':str(out),'scenes':53,'subtitles':len(subs),'script_chars':len(script),'sha256':digest}),flush=True)
    if '--apply' not in sys.argv:return
    completed=[]
    try:
        for table,before,changes in operations:
            live=fetch('std_projects',id='eq.'+PID)[0]
            if live != p:raise RuntimeError('Project changed or submitted during save; aborting')
            current=fetch(table,id='eq.'+before['id'])[0]
            if current!=before:raise RuntimeError('Concurrent row change; aborting')
            saved=patch_row(table,before,changes)
            completed.append((table,before,changes,saved))
            dump(out/'journal.json',{'completed':[{'table':t,'id':b['id'],'updated_at':s.get('updated_at')} for t,b,c,s in completed]})
    except Exception:
        for table,before,changes,saved in reversed(completed):
            patch_row(table,saved,{key:before.get(key) for key in changes})
        raise
    actual=fetch('std_projects',id='eq.'+PID)[0]
    assert actual['project_payload']['script']==script
    assert actual['source_payload']['pregenerated_script']==script
    assert [s['scene_text'] for s in fetch('std_project_scenes',project_id='eq.'+PID,order='scene_number.asc')]==sections
    dump(out/'verified.json',{'project_id':PID,'script_sha256':digest,'scene_count':53,'subtitles':len(subs),'verified':True})
    print('Saved and read-back verified',flush=True)

if __name__=='__main__':main()
