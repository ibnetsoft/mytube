"""Explicit track -> reviewed image generation -> rendered scene recovery, nine scenes only."""
import argparse,copy,dataclasses,hashlib,json,math,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'worker'),str(ROOT)]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env');os.environ['CODEX_CONTENT_MODEL']='gpt-5.5'
_popen=subprocess.Popen
def http_cli(command,*args,**kwargs):
 if isinstance(command,(list,tuple)) and Path(str(command[0])).name.lower() in ('codex','codex.exe','codex.cmd'):
  command=list(command)+['-c','model_provider="openai_http"','-c','model_providers.openai_http.name="OpenAI HTTP"','-c','model_providers.openai_http.wire_api="responses"','-c','model_providers.openai_http.requires_openai_auth=true','-c','model_providers.openai_http.supports_websockets=false']
 return _popen(command,*args,**kwargs)
subprocess.Popen=http_cli
from ae_media_utils import ffmpeg,run
from ae_mouth import digest,mouth_layers,review_layers,decode_scene_audio,amplitude_cues
from ae_video_tracking import track_video
from codex_content_runner import CodexStagedContentRunner
from manga_layer_generation import NativeCodexLayerGenerator
from PIL import Image,ImageDraw
DIR=ROOT/'output/codex-local-console/mouth-data-nine-3373'
data=json.loads((DIR/'mouth-data.json').read_text(encoding='utf8'))
config=json.loads((ROOT/'output/project-recovery-e9233112/subtitle-only-render-config.json').read_text(encoding='utf8'))
old=json.loads((ROOT/'output/project-recovery-e9233112/before-restored-audio-generation.json').read_text(encoding='utf8'));old=old.get('project_payload',old)
rows=[]
assert len(config['subtitles'])==len(old['subtitles'])==714
for current,saved in zip(config['subtitles'],old['subtitles']):
 assert current['text']==saved['text'],'Saved subtitle order/text changed'
 rows.append({**current,'speaker':saved.get('dialogue_speaker') or '', 'kind':saved.get('dialogue_kind') or ('dialogue' if saved.get('dialogue_speaker') else 'narration')})
def status(**value):
 (DIR/'processing-progress.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(value,ensure_ascii=False),flush=True)
def timing(number):
 selected=[r for r in rows if r['scene_number']==number];start=min(r['start'] for r in selected);end=max(r['end'] for r in selected)
 return start,end,selected
def track():
 for scene in data['scenes']:
  n=scene['number'];folder=DIR/f'processing-{n}';folder.mkdir(exist_ok=True)
  if (folder/'tracking-ready.json').exists():continue
  start,end,selected=timing(n);duration=end-start;frames=math.ceil(duration*24)
  clean=folder/'clean-moving-source.mp4'
  if not clean.exists():
   status(stage='track',scene=n,step='clean_source',duration=duration)
   # Minimal camera motion only: never recycle the existing faulty mouth composites.
   motion=f"zoompan=z='1+0.015*on/{max(1,frames-1)}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:s=1920x1080:fps=24"
   run([ffmpeg(),'-y','-i',str(DIR/f'scene-{n:03}.png'),'-vf',motion,'-frames:v',str(frames),'-c:v','h264_nvenc','-preset','p4','-pix_fmt','yuv420p',str(clean)])
  status(stage='track',scene=n,step='all_frames')
  first,speakers,report=track_video(clean,DIR/f'scene-{n:03}.png',scene['speakers'],folder/'tracking',duration,allow_partial=False)
  if report['frames_checked'] < frames-1:raise ValueError('All-frame tracking incomplete')
  receipt={'number':n,'start':start,'end':end,'duration':duration,'source_video':str(clean),'reference_image':str(first),'speakers':speakers,'report':report,'clean_source':True}
  (folder/'tracking-ready.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
  status(stage='track',scene=n,state='completed',frames=report['frames_checked'])
def images():
 runner=CodexStagedContentRunner();runner.config=dataclasses.replace(runner.config,timeout_seconds=240)
 generator=NativeCodexLayerGenerator(timeout_seconds=600)
 for scene in data['scenes']:
  n=scene['number'];folder=DIR/f'processing-{n}';tracked=json.loads((folder/'tracking-ready.json').read_text(encoding='utf8'))
  if (folder/'mouth-images-ready.json').exists():continue
  image=Path(tracked['reference_image']);speakers=tracked['speakers']
  for index,speaker in enumerate(speakers):
   status(stage='images',scene=n,speaker=speaker['speaker'])
   speaker['layers']=mouth_layers(generator,image,speaker,folder/f'poses-{index}')
  review_layers(runner,'nine-mouths-3373-'+str(n),image,speakers,folder)
  tracked['speakers']=speakers;(folder/'mouth-images-ready.json').write_text(json.dumps(tracked,ensure_ascii=False,indent=2),encoding='utf8')
  status(stage='images',scene=n,state='completed')
def render():
 import ae_highlight_worker as ae
 master=ROOT/'output/codex-local-console/ae-mouth/db93c4ef790211c53236f3ea8ca1655add9ff30e2156bb2af4dce8c98ebf5241/final-narration.mp3'
 audio_file=next(f for f in config['asset_manifest']['files'] if f['asset_type']=='audio')
 expected=audio_file.get('sha256') or audio_file.get('source_sha256') or audio_file.get('content_identity',{}).get('source_sha256')
 if not expected:raise ValueError('Final narration has no verified byte fingerprint')
 if digest(master)!=expected:raise ValueError('Final narration fingerprint changed')
 deliveries=[]
 for record in data['scenes']:
  n=record['number'];folder=DIR/f'processing-{n}';tracked=json.loads((folder/'mouth-images-ready.json').read_text(encoding='utf8'))
  output=folder/'final-with-voice.mp4'
  if output.exists() and (folder/'render-ready.json').exists():deliveries.append(json.loads((folder/'render-ready.json').read_text()));continue
  start,end,selected=timing(n);duration=end-start;samples=decode_scene_audio(ffmpeg(),master,start,duration)
  speakers=tracked['speakers']
  for speaker in speakers:speaker['cues']=amplitude_cues(samples,[r for r in selected if r['kind']=='dialogue' and r['speaker']==speaker['speaker']],start=start,duration=duration)
  scene={'scene_number':n,'duration_seconds':duration,'ae_motion_plan':{'enabled':True,'preset':'subtle_dialogue','vfx':[],'intensity':0,'motion':{'push':0,'drift_x':0,'drift_y':0,'shake':0}},'ae_mouth_runtime':{'enabled':True,'video_source':True,'speakers':speakers,'blinks':[]}}
  spec=ae.SceneJob(topic_id='3373-nine-mouth-repair',topic_title='3373 verified mouth recovery',structure={'scenes':[scene]},scene_index=0,scene=scene,scene_number=n,plan_kind='motion',preset='subtle_dialogue',duration_seconds=duration,source=ae.GcsRef('__local__',tracked['source_video']),source_type='project',project_payload={'ae_scene_delivery':'local'})
  status(stage='render',scene=n)
  rendered=ae._render_job(spec,keep_workdir=True)
  run([ffmpeg(),'-y','-i',rendered['local_path'],'-ss',str(start),'-i',str(master),'-t',str(duration),'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',str(output)])
  receipt={'number':n,'path':str(output),'sha256':digest(output),'duration':duration,'audio_start':start,'audio_asset_id':audio_file['content_identity']['audio_asset_id'],'rendered':True,'uploaded':False}
  (folder/'render-ready.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8');deliveries.append(receipt)
  status(stage='render',scene=n,state='completed')
 (DIR/'nine-render-deliveries.json').write_text(json.dumps(deliveries,ensure_ascii=False,indent=2),encoding='utf8')
parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['track','images','render']);args=parser.parse_args()
try:globals()[args.phase]();status(stage=args.phase,state='completed',scenes=[s['number'] for s in data['scenes']])
except Exception as exc:status(stage=args.phase,state='failed',error=str(exc));raise
