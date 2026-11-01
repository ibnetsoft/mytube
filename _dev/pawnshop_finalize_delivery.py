"""Finalize source-bound production defaults while preserving live immutable media links."""
import copy,hashlib,json,sys,zipfile
from pathlib import Path
from datetime import datetime,timezone
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')];load_dotenv(ROOT/'worker/connection.env')
from worker.script_worker_store import ScriptStore
P=ROOT/'output/pawnshop-series/episode-01/production';D=ROOT/'docs/pawnshop-series/episode-01';store=ScriptStore()
t=store.request('GET','topics_queue',params={'id':'eq.3387','select':'id,status,assigned_employee_email,pregenerated_script,pregenerated_structure,progress_payload'})[0][0]
assert t['status']=='pending' and not t.get('assigned_employee_email')
sha=hashlib.sha256(t['pregenerated_script'].encode()).hexdigest();assert sha=='56035b9835d2c17bfdb0fa916c9da3be3b458595921a920061b622fd59c9d328'
planned=json.loads((P/'production-structure-with-defaults.json').read_text());live=t['pregenerated_structure'];merged=copy.deepcopy(live)
for k,v in planned.items():
 if k!='scenes':merged[k]=copy.deepcopy(v)
asset_keys={'image_url','asset_status','local_layer_status','psd_layer_status','metadata'}
for scene,p in zip(merged['scenes'],planned['scenes']):
 assert scene['scene_number']==p['scene_number'] and scene['scene_text']==p['scene_text']
 for k,v in p.items():
  if k not in asset_keys:scene[k]=copy.deepcopy(v)
 md=scene.get('metadata',{});scene['metadata']={**p.get('metadata',{}),**md}
 assert scene.get('image_url') and scene['metadata']['cowork_image_asset']['storage_readback_verified']
 if 19<=scene['scene_number']<=50:
  assert scene['metadata']['psd_layer_asset']['storage_readback_verified']
  assert len(scene['metadata']['local_layer_asset']['assets'])>=3
assert len(merged['scenes'])==144
assert 'slow_push_in' not in json.dumps(merged)
notes='''
## 2026-11-02 실제 이미지 납품 검증

- 실제 단일 이미지 112장(1~18, 51~144), 19~50씬 합성 이미지 32장, 독립 생성 PNG 레이어 104개, 실제 다층 PSD 32개를 저장하고 웹 주제 #3387에 연결했다.
- 저장소 파일은 업로드 후 다시 읽어 SHA256을 대조했다. PSD는 생성 후 다시 열어 레이어 구조를 확인했다. 프롬프트 개수를 파일 완성 증거로 대신하지 않았다.
- 144씬 JA 원문과 SHA를 대조한 KO/TH 검토 번역을 로컬 Codex CLI로 생성했다. 실제 녹음 기준 타임코드 자막은 아직 없다.
- 고정 카메라 기본, 필요 장면만 3초 이동과 전후 정지로 정리했다. 7개 구간 BGM 프롬프트와 기존 SFX 지시문을 저장했다. 실제 음악·TTS·AE 렌더 영상은 이번 대본/이미지 납품에 포함되지 않았다.

### 실제 시각 검수의 미해결 사항

- 19~50 전체 합성 콘택트시트를 확인했다. 25씬 서류 크기가 과도하고, 27/32씬 전경 사진이 얼굴을 많이 가린다. 30/43/47/49/50씬에는 배경에 인물 일부가 남아 독립 인물 레이어와 중복되어 보일 수 있다. 36/44씬 전경 테이블의 높이·크기가 배경 원근과 다르다. 24씬 의자가 중복된다.
- 26/28/33씬 전경의 살아 있는 인물 혼입, 30씬 인물 레이어의 다른 인물·시계 혼입, 32씬 인물 레이어의 소품 혼입은 별도 이미지 편집으로 분리했다. 인쇄 사진 속 인물은 사진 내용으로 유지했다.
- 일부 초기 단일 이미지의 시계(3/15/16씬)와 인물 얼굴 버전·사진 내용에 연속성 차이가 있다. Nao V2/V3 혼용 및 기존 얼굴 등록부와의 유사/불확실 판정을 품질 통과로 바꾸지 않았다.
- 파일·알파·PSD 저장 성공은 최종 미술 품질 승인이나 실제 AE 렌더 검수 통과를 뜻하지 않는다. 위 사항은 사용자 지침에 따라 납품을 중단하지 않고 기록한다.
- 35분은 계획값이다. 실제 녹음·최종 영상 길이는 아직 검증되지 않았다. 관리자 게시와 YouTube 업로드는 별도 작업이다.
'''
q=D/'QUALITY_NOTES.md';text=q.read_text();text=text.replace('대본·씬별 이미지 프롬프트·레이어 프롬프트·소개문을 준비했으며 씬 이미지, TTS, 영상 렌더는 미완료.','대본·씬 이미지·분리 레이어·PSD·검토 번역·연출 지시문 납품 완료. TTS와 영상 렌더는 미실행.').replace('등록 상태: 제작 대기. 실제 이미지·TTS·영상 렌더 미완료.','등록 상태: 제작 대기. 실제 씬 이미지와 레이어/PSD 연결 완료. TTS·영상 렌더 미실행.')
if '## 2026-11-02 실제 이미지 납품 검증' not in text:text+='\n'+notes
q.write_text(text)
progress=copy.deepcopy(t.get('progress_payload') or {});progress.update({'scene_image_count':144,'image_generation_status':'completed','scene_assets_ready':True,'independent_png_plane_count':104,'layered_psd_count':32,'scene_review_translation_languages':['ko','th'],'review_translation_source':'local_codex_cli','quality_notes_report':'docs/pawnshop-series/episode-01/QUALITY_NOTES.md','image_quality_review':'findings_recorded_not_all_approved','has_tts_audio':False,'tts_completed':False,'subtitles_completed':False,'final_video_rendered':False,'production_assets_completed_at':datetime.now(timezone.utc).isoformat()})
store.request('PATCH','topics_queue',params={'id':'eq.3387','status':'eq.pending','assigned_employee_email':'eq.'},body={'pregenerated_structure':merged,'progress_payload':progress})
a=store.request('GET','topics_queue',params={'id':'eq.3387','select':'pregenerated_script,pregenerated_structure,progress_payload'})[0][0];assert a['pregenerated_structure']==merged and a['progress_payload']['scene_image_count']==144
(P/'final-live-topic-3387.json').write_text(json.dumps(a,ensure_ascii=False,indent=2))
manifest={'topic_id':3387,'script_sha256':sha,'scene_images':144,'single_images':112,'layer_composites':32,'independent_png_planes':104,'layered_psds':32,'web_database_readback_verified':True,'quality_findings_recorded':True,'tts_rendered':False,'video_rendered':False,'files':[]}
files=[]
for folder in sorted((P/'singles').iterdir()):
 rs=[json.loads(f.read_text()) for f in folder.glob('*.json')]
 if rs:files.append((Path(max(rs,key=lambda r:r['generated_at'])['path']),'images/'+folder.name+'.png'))
for n,p in json.loads((P/'composite-packages.json').read_text()).items():
 files.extend([(Path(p['image']),f'images/{int(n):03d}.png'),(Path(p['psd']),f'psd/{int(n):03d}.psd')])
 for layer in p['layers']:files.append((Path(p['folder'])/layer['file'],f'layers/{int(n):03d}/{layer["role"]}.png'))
for f in D.glob('*.md'):files.append((f,'documents/'+f.name))
files.append((P/'final-live-topic-3387.json','production-records.json'))
for f,name in files:manifest['files'].append({'path':name,'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size})
(P/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
z=P.parent/'EPISODE_01_DELIVERY.zip'
with zipfile.ZipFile(z,'w',compression=zipfile.ZIP_STORED) as bundle:
 for f,name in files:bundle.write(f,name)
 bundle.write(P/'DELIVERY_MANIFEST.json','DELIVERY_MANIFEST.json')
with zipfile.ZipFile(z) as bundle:assert bundle.testzip() is None and len(bundle.namelist())==len(files)+1
print(json.dumps({**{k:v for k,v in manifest.items() if k!='files'},'bundle':str(z),'bundle_bytes':z.stat().st_size},ensure_ascii=False))
