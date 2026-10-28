import sqlite3, pathlib, pickle, json
p=pathlib.Path('data/wingsai.db')
if p.exists():
 c=sqlite3.connect('file:'+str(p.resolve())+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
 try:
  print('channels', json.dumps([dict(r) for r in c.execute('select id,name,handle,credentials_path from channels')],ensure_ascii=False))
 except Exception as e: print(type(e).__name__)
with open('tokens/token_1.pickle','rb') as f: creds=pickle.load(f)
print('existing_oauth',json.dumps({'valid':creds.valid,'expired':creds.expired,'scopes':creds.scopes,'has_refresh':bool(creds.refresh_token)}))
