"""Read actual recording runtime; never infer it from the last caption."""
import os
import re
import requests
from worker.youtube_transcript import video_id_from_url


def duration_seconds(value):
    m=re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',str(value or ''))
    seconds=sum(int(v or 0)*unit for v,unit in zip(m.groups(),(3600,60,1))) if m else 0
    if not 60<=seconds<=3600:raise ValueError('원본 영상 길이를 확인할 수 없거나 지원 범위(1~60분)를 벗어났습니다.')
    return seconds


def source_metadata(url):
    identity=video_id_from_url(url)
    values=[os.getenv('YOUTUBE_API_KEY',''),os.getenv('YOUTUBE_API_KEYS','')]
    try:
        from worker.script_worker_store import ScriptStore
        rows,_=ScriptStore().request('GET','global_settings',params={'select':'key,value','key':'in.(sys_api_youtube,sys_api_youtube_keys)'})
        values.extend(str(r.get('value') or '') for r in rows)
    except Exception:pass
    keys=list(dict.fromkeys(k for value in values for k in re.split(r'[\s,;]+',value) if k))[:3]
    for key in keys:
        try:
            response=requests.get('https://www.googleapis.com/youtube/v3/videos',params={'part':'contentDetails,snippet','id':identity,'key':key},timeout=(5,12))
            if not response.ok:continue
            row=next((r for r in response.json().get('items',[]) if r.get('id')==identity),None)
            if not row or row.get('snippet',{}).get('liveBroadcastContent')=='live':raise ValueError('공개 녹화 영상의 길이를 확인해 주세요.')
            return {'source_video_id':identity,'source_duration_seconds':duration_seconds(row.get('contentDetails',{}).get('duration')),'source_duration_verified':True}
        except (requests.RequestException,KeyError):continue
    raise ValueError('YouTube 원본 영상 길이를 확인하지 못했습니다. API 설정을 확인하세요. 임의 길이로 생성하지 않았습니다.')
