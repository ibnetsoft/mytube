"""Reviewed Thai localization, preserving every original subtitle and asset."""
import copy,hashlib,json
from datetime import datetime,timezone
import requests
from check_3292_current import capture
from draft_3292_scoped import OUT,PID,UID,save
from scripts.repair_existing_topic_scripts import _headers

def main():
    assert not (OUT/'thai-review-journal.json').exists(),'Inspect journal before rerun'
    before=capture();p=before['project'];q=before['topic'][0];payload=copy.deepcopy(p['project_payload'])
    save('before-thai-review.json',before)
    subs=payload['subtitles'];th=payload['subtitle_translations']['th'];blocks=th['blocks']
    assert len(subs)==len(blocks)==263
    for i,(s,b) in enumerate(zip(subs,blocks)):
        assert b['index']==i and b['source_text'].strip()==s['text'].strip()
        assert b['scene_number']==s['scene_number'] and b['translated_text'].strip()
    fixes={54:'ให้หลังจะนำค่าจ้างมาแลกคืนนั้น ยังระบุรอยบัดกรี',55:'รูปพระจันทร์ครึ่งเสี้ยวที่ด้านในห่วงไว้ด้วย',
           110:'กึมรเยที่นอนอยู่ก็'}
    for i,value in fixes.items():blocks[i]['translated_text']=value
    now=datetime.now(timezone.utc).isoformat();sha=hashlib.sha256(payload['script'].encode()).hexdigest()
    th.update(updated_at=now,reviewed_at=now,source_script_sha256=sha,review_status='reviewed',reviewed_block_count=263)
    title='ต่างหูที่หล่นกับคำสาปที่ตามหลอกหลอนครอบครัวมาสามชั่วอายุคน'
    meta={'title':title,'description':'เรื่องเล่าเกาหลีที่แต่งขึ้น ยอนอี หญิงสาวรับจ้างเย็บผ้า ถูกกล่าวหาว่าเป็นขโมยเพราะต่างหูเงินที่หล่นจากซับในเสื้อเก่าของบ้านเศรษฐี แต่ต่างหูข้างนั้นกลับเป็นหลักฐานของความอยุติธรรมที่ตามหลอกหลอนกึมรเยผู้เป็นยายและซุนด็อกผู้เป็นแม่ ทั้งสามค่อย ๆ ตามรอยเอกสารที่ซ่อนไว้และร่องรอยในเสื้อ เพื่อเปิดเผยความจริงเรื่องข้อกล่าวหาเท็จและสวนหม่อนที่ถูกยึดไป',
      'tags':['นิทานเกาหลี','เรื่องเล่าที่แต่งขึ้น','นิทานสอนใจ','ความยุติธรรม','เรื่องราวครอบครัว','แม่และลูก','ยายและหลาน','ต่างหูเงิน','ช่างเย็บผ้า','ยุคโชซอน','ข้อกล่าวหาเท็จ','สวนหม่อน','ความจริง','เรื่องเล่าซึ้งใจ','เรื่องเล่าโบราณ'],
      'hashtags':['#นิทานเกาหลี','#เรื่องเล่าโบราณ','#ความยุติธรรม','#เรื่องราวครอบครัว','#ต่างหูเงิน'],
      'thumbnail_text':'ความจริงของต่างหู','language':'th','source_script_sha256':sha}
    payload['publish_metadata_translations']={**payload.get('publish_metadata_translations',{}),'th':meta}
    payload['localization_review']={'language':'th','reviewed_at':now,'blocks':263,'scenes':53,'source_script_sha256':sha,'voice_language':'ko'}
    source=copy.deepcopy(p['source_payload']);source.update(topic_th=title,category_name_th='นิทานโบราณ')
    source['publish_metadata_translations']={**source.get('publish_metadata_translations',{}),'th':meta}
    qp=copy.deepcopy(q.get('progress_payload') or {});qp['localization_review']=payload['localization_review'];qp['publish_metadata_translations']={**qp.get('publish_metadata_translations',{}),'th':meta}
    qpatch={'topic_th':title,'category_name_th':'นิทานโบราณ','translated_at':now,'progress_payload':qp}
    ppatch={'project_payload':payload,'source_payload':source,'updated_at':now}
    base,headers=_headers();journal=[]
    fresh=capture();assert fresh['project']==p and fresh['topic'][0]==q,'Concurrent edit'
    for table,old,body in [('topics_queue',q,qpatch),('std_projects',p,ppatch)]:
        params={'id':'eq.'+str(old['id'])}
        if old.get('updated_at'):params['updated_at']='eq.'+old['updated_at']
        if table=='std_projects':params.update(user_id='eq.'+UID,submitted_at='is.null',status='in.(claimed,in_progress)')
        r=requests.patch(base+'/rest/v1/'+table,params=params,headers={**headers,'Prefer':'return=representation'},json=body,timeout=90)
        r.raise_for_status();assert len(r.json())==1
        journal.append({'table':table,'before':old,'after':r.json()[0]});save('thai-review-journal.json',journal)
    after=capture()
    assert after['project']['project_payload']==payload and after['project']['source_payload']==source
    assert after['topic'][0]['topic_th']==title
    assert payload['subtitles']==p['project_payload']['subtitles'] and payload['structure']==p['project_payload']['structure']
    assert payload['script']==p['project_payload']['script']
    save('thai-reviewed.json',{'metadata':meta,'subtitle_translation':th,'verification':payload['localization_review']})
    print('Thai verified:263 blocks,53 scenes; title/category/metadata saved; source script and assets unchanged.')

if __name__=='__main__':main()
