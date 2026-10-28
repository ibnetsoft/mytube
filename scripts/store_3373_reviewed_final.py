import sys,json
from pathlib import Path
sys.path[:0]=['worker'];from dotenv import load_dotenv;load_dotenv('.env')
import ae_highlight_worker as ae
p=Path('output/project-recovery-e9233112');f=p/'reviewed-final-local/output.mp4';r=p/'reviewed-final-storage.json'
if not r.exists():
 bucket,key,url=ae._upload_gcs_file(f,'std-projects/e9233112-f0d7-4b35-91bf-2f892844eb30/final-renders/v10-reviewed-101-scenes.mp4','video/mp4');r.write_text(json.dumps({'bucket':bucket,'path':key,'url':url,'bytes':f.stat().st_size}),encoding='utf8')
print('FINAL_STORAGE_COMPLETE',flush=True)
