"""Representative-first recovery of original-image speaker geometry, no publishing."""
import dataclasses,json,os,shutil,subprocess,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
os.environ['CODEX_CONTENT_MODEL']='gpt-5.5'
original_popen=subprocess.Popen
def cli_http(command,*args,**kwargs):
 if isinstance(command,(list,tuple)) and Path(str(command[0])).name.lower() in ('codex','codex.exe','codex.cmd'):
  command=list(command)+['-c','model_provider="openai_http"','-c','model_providers.openai_http.name="OpenAI HTTP"','-c','model_providers.openai_http.wire_api="responses"','-c','model_providers.openai_http.requires_openai_auth=true','-c','model_providers.openai_http.supports_websockets=false']
 return original_popen(command,*args,**kwargs)
subprocess.Popen=cli_http
from codex_content_runner import CodexStagedContentRunner
from ae_mouth import locate_speakers,digest
from PIL import Image,ImageDraw
DIR=ROOT/'output/codex-local-console/mouth-geometry-v2-3373'
DIR.mkdir(parents=True,exist_ok=True)
project=json.loads((ROOT/'output/project-recovery-e9233112/before-restored-audio-generation.json').read_text(encoding='utf8'))
payload=project.get('project_payload',project)
cast={'main':payload['structure'].get('main_character',{}),'supporting':payload['structure'].get('supporting_characters',[]),'scene_cast':payload['structure'].get('scene_cast',[])}
targets={26:['大五郎','お鈴'],37:['大五郎'],51:['お鈴'],53:['大五郎']}
runner=CodexStagedContentRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=180)
results={}
for number,names in targets.items():
 directory=DIR/f'scene-{number}';directory.mkdir(exist_ok=True)
 image=directory/'original.png';shutil.copyfile(ROOT/f'_dev/artifacts/final_3373_current_v4/images/scene_{number:03}.png',image)
 receipt=directory/'geometry.json'
 if receipt.exists():results[number]=json.loads(receipt.read_text());continue
 print(json.dumps({'scene':number,'stage':'original_face_geometry'},ensure_ascii=False),flush=True)
 try:
  text=' '.join(r['text'] for r in payload['subtitles'] if r.get('scene_number')==number)
  rows=[{'kind':'dialogue','speaker':name} for name in names]
  speakers=locate_speakers(runner,'geometry-v2-3373-'+str(number),{'number':number,'text':text},image,rows,cast)
  result={'number':number,'source_sha256':digest(image),'speakers':speakers,'state':'ready','representative_coordinate_test':True}
  receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
  with Image.open(image) as base:
   marked=base.convert('RGB');draw=ImageDraw.Draw(marked)
   for s in speakers:
    if s.get('mouth_box'):
     b=s['mouth_box'];draw.rectangle([b[0]*base.width,b[1]*base.height,b[2]*base.width,b[3]*base.height],outline='lime',width=3)
    for p in (s.get('mouth_geometry',{}).get('landmarks') or {}).values():
     if isinstance(p,list) and len(p)==2:
      x,y=p[0]*base.width,p[1]*base.height;draw.ellipse([x-4,y-4,x+4,y+4],fill='red')
   marked.save(directory/'geometry-overlay.png')
  results[number]=result;print(json.dumps({'scene':number,'state':'ready','speakers':[{'name':s['speaker'],'status':s['status'],'pose':s.get('mouth_geometry',{}).get('orientation'),'policy':s.get('mouth_geometry',{}).get('render_policy')} for s in speakers]},ensure_ascii=False),flush=True)
 except Exception as e:
  results[number]={'number':number,'state':'needs_review','error':str(e)}
  print(json.dumps(results[number],ensure_ascii=False),flush=True)
(DIR/'representative-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
if any(r['state']!='ready' for r in results.values()):raise SystemExit(2)
