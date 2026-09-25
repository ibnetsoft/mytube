"""Scoped punctuation-only repair with annotation offsets, CAS and readback."""
import copy,hashlib,json,sys
from datetime import datetime,timezone
import requests
from check_3292_current import capture
from draft_3292_scoped import OUT,UID,save
from scripts.repair_existing_topic_scripts import _headers

QUOTES=set('\"\'“”‘’「」『』＂＇«»‹›„‟‚‛')
FIELDS={'script','original_worker_script','pregenerated_script','scene_text','narration','script_excerpt','source_text','translated_text','text'}
def clean(text):return ''.join(c for c in text if c not in QUOTES)
def sha(text):return hashlib.sha256(text.encode()).hexdigest()
def transform(value):
    if isinstance(value,list):return [transform(x) for x in value]
    if not isinstance(value,dict):return value
    result=copy.deepcopy(value)
    # Annotation spans are indexed in original Unicode codepoints.
    if isinstance(value.get('source_text'),str) and isinstance(value.get('spans'),list):
        original=value['source_text']; result['source_text']=clean(original)
        result['source_sha256']=sha(result['source_text'])
        for old,new in zip(value['spans'],result['spans']):
            assert original[old['start']:old['end']]==old['text']
            new.update(start=len(clean(original[:old['start']])),end=len(clean(original[:old['end']])),text=clean(old['text']))
            assert result['source_text'][new['start']:new['end']]==new['text']
        return result
    for key,item in value.items():
        if key in FIELDS and isinstance(item,str):result[key]=clean(item)
        elif isinstance(item,(list,dict)):result[key]=transform(item)
    return result

def main(apply=False):
    assert not (OUT/'quote-removal-journal.json').exists(),'Inspect previous journal'
    before=capture();p=before['project'];q=before['topic'][0]
    assert len(before['linked_projects'])==1
    payload=transform(p['project_payload']);source=transform(p['source_payload']);qstructure=transform(q['pregenerated_structure'])
    newsha=sha(payload['script']);now=datetime.now(timezone.utc).isoformat()
    revision={'kind':'punctuation_only','removed':'single_and_double_quotation_marks','applied_at':now,'previous_script_sha256':sha(p['project_payload']['script']),'script_sha256':newsha}
    payload['quote_removal_revision']=revision;source['quote_removal_revision']=revision;qstructure['quote_removal_revision']=revision
    for lang,translation in payload.get('subtitle_translations',{}).items():
        assert len(translation['blocks'])==len(payload['subtitles'])
        translation.update(source_script_sha256=newsha,updated_at=now)
        for i,(sub,block) in enumerate(zip(payload['subtitles'],translation['blocks'])):
            assert sub['text'].strip() and block['translated_text'].strip(),'Empty block after removal'
            assert block['index']==i and sub['text'].strip()==block['source_text'].strip()
    if payload.get('localization_review'):payload['localization_review']['source_script_sha256']=newsha
    qpatch={'pregenerated_script':clean(q['pregenerated_script']),'pregenerated_structure':qstructure}
    ppatch={'project_payload':payload,'source_payload':source,'updated_at':now}
    ops=[]
    for row in before['scene_rows']:
        new=transform(row);body={k:v for k,v in new.items() if row[k]!=v}
        if body:ops.append((row,{**body,'updated_at':now}))
    # Punctuation only: media, timings, speaker identity and text content stay intact.
    assert len(payload['subtitles'])==len(p['project_payload']['subtitles'])==263
    assert len(payload['structure']['scenes'])==53
    for old,new in zip(p['project_payload']['subtitles'],payload['subtitles']):
        assert {k:v for k,v in old.items() if k!='text'}=={k:v for k,v in new.items() if k!='text'}
        assert clean(old['text'])==new['text'] and not QUOTES.intersection(new['text'])
    for old,new in zip(p['project_payload']['structure']['scenes'],payload['structure']['scenes']):
        for k in ('image_url','video_url','image_prompt','video_prompt','start_time','end_time','duration_seconds'):
            assert old.get(k)==new.get(k)
    summary={'topic':3292,'scenes':53,'subtitles':263,'script_quotes_removed':len(p['project_payload']['script'])-len(payload['script']),
      'subtitle_blocks_changed':sum(a['text']!=b['text'] for a,b in zip(p['project_payload']['subtitles'],payload['subtitles'])),
      'scene_rows_changed':len(ops),'assets_preserved':True,'dialogue_offsets_verified':True}
    save('quote-removal-plan.json',{'project_patch':ppatch,'topic_patch':qpatch,'scene_ops':ops,'summary':summary})
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if not apply:return
    save('before-quote-removal.json',before)
    fresh=capture()
    for k in ['project','topic','scene_rows']:
        a,b=fresh[k],before[k]
        if isinstance(a,list):a=sorted(a,key=lambda x:x['id']);b=sorted(b,key=lambda x:x['id'])
        assert a==b,'Concurrent edit: '+k
    base,headers=_headers();journal=[]
    def patch(table,old,body):
        params={'id':'eq.'+str(old['id'])}
        if old.get('updated_at'):params['updated_at']='eq.'+old['updated_at']
        if table=='std_projects':params.update(user_id='eq.'+UID,submitted_at='is.null',status='in.(claimed,in_progress)')
        r=requests.patch(base+'/rest/v1/'+table,params=params,headers={**headers,'Prefer':'return=representation'},json=body,timeout=90)
        r.raise_for_status();assert len(r.json())==1,'CAS failed '+table
        journal.append({'table':table,'old':old,'new':r.json()[0]});save('quote-removal-journal.json',journal)
    for old,body in ops:patch('std_project_scenes',old,body)
    patch('topics_queue',q,qpatch);patch('std_projects',p,ppatch)
    after=capture();save('after-quote-removal.json',after)
    assert after['project']['project_payload']==payload and after['project']['source_payload']==source
    for k,v in qpatch.items():assert after['topic'][0][k]==v
    for old,body in ops:
        actual=next(x for x in after['scene_rows'] if x['id']==old['id'])
        for k,v in body.items():
            if k!='updated_at':assert actual[k]==v
    assert after['assets']==before['assets']
    summary.update(db_verified=True,script_sha256=newsha);save('quote-removal-verification.json',summary)
    print('DB readback verified; quotes removed, all scene assets preserved.',flush=True)

if __name__=='__main__':main('--apply' in sys.argv)
