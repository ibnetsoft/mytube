import pathlib,json,pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
root=pathlib.Path(__file__).resolve().parents[1]
scopes=['https://www.googleapis.com/auth/youtube.upload','https://www.googleapis.com/auth/youtube']
flow=InstalledAppFlow.from_client_secrets_file(str(root/'client_secret.json'),scopes)
original=flow.authorization_url
def announce(*args,**kwargs):
 result=original(*args,**kwargs)
 (root/'_dev/artifacts/honjada_google_signin.json').write_text(json.dumps({'authorization_url':result[0]}),encoding='utf8')
 print('Google sign-in window ready',flush=True)
 return result
flow.authorization_url=announce
try:
 creds=flow.run_local_server(host='localhost',port=0,open_browser=False,authorization_prompt_message='',success_message='AIR Studio: Google login received. Checking requested YouTube channel.',timeout_seconds=1800)
 rows=build('youtube','v3',credentials=creds,cache_discovery=False).channels().list(part='snippet',mine=True).execute().get('items',[])
 match=next((r for r in rows if r['snippet'].get('customUrl','').lower()=='@honjada-y8n'),None)
 if not match: raise RuntimeError('The signed-in channel is not @Honjada-y8n. Credentials were not saved.')
 with (root/'tokens/token_1.pickle').open('wb') as f:pickle.dump(creds,f)
 receipt={'authenticated':True,'local_channel_id':1,'youtube_channel_id':match['id'],'title':match['snippet']['title'],'handle':match['snippet']['customUrl']}
 (root/'_dev/artifacts/honjada_verified_oauth.json').write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf8')
 print('Verified and saved @Honjada-y8n authorization',flush=True)
except Exception as e:
 print('Authorization did not finish: '+type(e).__name__,flush=True)
 raise SystemExit(1)
