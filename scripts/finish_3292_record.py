"""Link verified private package and record observed UI checks, without changing content."""
import json
from datetime import datetime, timezone
import requests
from draft_3292_scoped import OUT, PID, save
from scripts.audit_active_content import fetch
from scripts.repair_existing_topic_scripts import _headers

p=fetch('std_projects',id=f'eq.{PID}')[0]
assert p['project_payload']['approved_script_revision']['script_sha256']=='79e865def1d9692b937bb4bdc37298aaaae50717974d36a1373c86e2de669d5c'
assert p['status'] in ('claimed','in_progress') and not p.get('submitted_at')
drive=json.loads((OUT/'drive-package.json').read_text(encoding='utf-8'))
now=datetime.now(timezone.utc).isoformat()
verification={'verified_at':now,'account':'supapitmusic@gmail.com','project_id':PID,
    'subtitle_blocks':263,'scenes':53,'displayed_duration':'15:00','edited_dialogue_visible':True,
    'first_scene_image_visible':True,'video_prompts_visible':12,'character_images_visible':3,
    'body_images':37,'body_image_total':41,'missing_images':[21,22,23,24],
    'required_video_clips':0,'required_video_total':12,'playback_tested':False,
    'note':'Read-only UI inspection. No playback/TTS generation/save action triggered. Thumbnail header badge is not final-save verification.'}
save('web-verification.json',verification)
progress={**p['progress_payload'],'visual_package_drive':drive,'repair_web_verification':verification}
base,headers=_headers();headers={**headers,'Prefer':'return=representation'}
save('before-package-link.json',p)
r=requests.patch(f'{base}/rest/v1/std_projects',params={'id':f'eq.{PID}','updated_at':f'eq.{p["updated_at"]}',
    'submitted_at':'is.null','status':'in.(claimed,in_progress)'},headers=headers,
    json={'progress_payload':progress,'updated_at':now},timeout=90)
r.raise_for_status();assert len(r.json())==1
actual=fetch('std_projects',id=f'eq.{PID}')[0]
assert actual['progress_payload']['visual_package_drive']==drive
assert actual['project_payload']==p['project_payload']
report=json.loads((OUT/'db-verification.json').read_text(encoding='utf-8'))
report.update(user_web_verified=True,web_verification=verification,drive_package_verified=True)
save('db-verification.json',report)
print('Verified package linked; content unchanged; UI evidence recorded.',flush=True)
