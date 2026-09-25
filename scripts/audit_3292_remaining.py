"""Read-only live inventory for remaining localization and delivery work."""
import json
from check_3292_current import capture
from draft_3292_scoped import OUT,save

def main():
    data=capture();save('remaining-live.json',data)
    p=data['project'];q=data['topic'][0];v=p['project_payload']
    for name,obj in [('project_payload',v),('progress',p['progress_payload']),('topic',q)]:
        print(name,[(k,type(x).__name__,len(x) if isinstance(x,(dict,list,str)) else x) for k,x in obj.items()])
    for key in ['subtitle_translations','translation','thumbnail','tts','audio']:
        x=v.get(key)
        print(key,json.dumps(x,ensure_ascii=False)[:4500])
    print('sample_subtitles',json.dumps(v.get('subtitles',[])[:3],ensure_ascii=False)[:5000])
    print('asset_summary',[(a.get('asset_type'),a.get('scene_number'),list(a)) for a in data['assets']][:5])

if __name__=='__main__':main()
