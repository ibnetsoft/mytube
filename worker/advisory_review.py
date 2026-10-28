"""Keep truthful quality findings while completing a playable deliverable."""
import copy
POLICY = 'complete_with_notes/v1'
AUTHORIZATION = 'user_requested_2026-10-28'
def enabled(snapshot):
    return snapshot.get('_advisory_review') is True or snapshot.get('execution_policy',{}).get('review_policy') == POLICY
def note(snapshot, scene, stage, detail):
    item = {'scene_number':scene.get('number'), 'stage':stage, 'detail':str(detail)[:4000]}
    notes = snapshot.setdefault('_quality_notes', [])
    if item not in notes: notes.append(item)
    return item
def fixed_plan(snapshot, scene, detail):
    prepared = copy.deepcopy(scene.get('prepared_direction'))
    if not isinstance(prepared,dict):
        raise ValueError('실행 가능한 저장 연출이 없습니다: '+str(detail))
    prepared['source'] = scene['source_kind']
    note(snapshot,scene,'direction',detail)
    return {'number':scene['number'],'scene':prepared,'ai':None,'evidence':['Saved direction used; see quality notes'],
            'continuity':{k:'Existing source preserved' for k in ('entry','exit','screen_direction','lighting')},'quality_advisory':True}
