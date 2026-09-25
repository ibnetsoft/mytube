"""Fresh scoped pre-application snapshot, no writes to production."""
import json
from datetime import datetime, timezone
from draft_3292_scoped import OUT, PID, UID, save
from scripts.audit_active_content import fetch

def capture():
    p=fetch('std_projects',id=f'eq.{PID}')[0]
    assert p['user_id']==UID and p['topic_queue_id']==3292
    assert p['status'] in ('claimed','in_progress') and not p.get('submitted_at')
    return {'project':p,'topic':fetch('topics_queue',id='eq.3292'),
        'scene_rows':fetch('std_project_scenes',project_id=f'eq.{PID}'),
        'assets':fetch('std_project_assets',project_id=f'eq.{PID}'),
        'linked_projects':fetch('std_projects',topic_queue_id='eq.3292'),
        'captured_at':datetime.now(timezone.utc).isoformat()}

if __name__=='__main__':
    current=capture()
    before=json.loads((OUT/'source.json').read_text(encoding='utf-8'))
    assert current['project']==before['project'],'Project changed; stop'
    assert current['topic']==before['topic'],'Topic changed; stop'
    assert sorted(current['scene_rows'],key=lambda x:x['id'])==sorted(before['scene_rows'],key=lambda x:x['id']),'Scenes changed; stop'
    assert len(current['linked_projects'])==1,'Shared topic; stop for scope review'
    if not (OUT/'preapply-source.json').exists():save('preapply-source.json',current)
    print(json.dumps({'unchanged':True,'scenes':len(current['scene_rows']),
        'assets':[{'id':a.get('id'),'type':a.get('asset_type'),'scene_id':a.get('scene_id'),'scene_number':a.get('scene_number')} for a in current['assets']],
        'asset_keys':list(current['assets'][0]) if current['assets'] else [],
        'linked_projects':len(current['linked_projects'])},ensure_ascii=False))
