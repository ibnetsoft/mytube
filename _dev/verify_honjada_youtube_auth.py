import pickle,json
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
with open('tokens/token_1.pickle','rb') as f: creds=pickle.load(f)
try:
 if not creds.valid: creds.refresh(Request())
 yt=build('youtube','v3',credentials=creds,cache_discovery=False)
 rows=yt.channels().list(part='snippet,status',mine=True).execute().get('items',[])
 result=[{'youtube_channel_id':r['id'],'title':r['snippet']['title'],'handle':r['snippet'].get('customUrl'),
          'long_upload_status':r.get('status',{}).get('longUploadsStatus'),
          'is_linked':r.get('status',{}).get('isLinked')} for r in rows]
 print(json.dumps({'authenticated':True,'channels':result},ensure_ascii=False))
 if not any(str(r.get('handle','')).lower()=='@honjada-y8n' for r in result): raise RuntimeError('Authenticated channel differs from requested handle')
 with open('tokens/token_1.pickle','wb') as f: pickle.dump(creds,f)
 open('_dev/artifacts/honjada_verified_oauth.json','w',encoding='utf8').write(json.dumps({'authenticated':True,'local_channel_id':1,'channels':result},ensure_ascii=False))
except Exception as e:
 print(json.dumps({'authenticated':False,'error_type':type(e).__name__,'needs_google_sign_in':True}))
 raise SystemExit(2)
