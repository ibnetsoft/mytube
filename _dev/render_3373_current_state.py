import sys,json,copy,shutil,hashlib,subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
for f in ['.env','.env.local','auth-web/.env.local']:load_dotenv(ROOT/f)
from worker.script_worker_store import ScriptStore
from worker.ae_highlight_worker import _download_gcs_file,GcsRef
from worker.ae_mouth import assess_dialogue
from worker.codex_content_runner import CodexStagedContentRunner
from worker.lipsync_video_worker import ffmpeg
from services.ffmpeg_slideshow_service import render_ffmpeg_slideshow
store=ScriptStore();pid='e9233112-f0d7-4b35-91bf-2f892844eb30';out=ROOT/'_dev/artifacts/final_3373_current_v4';out.mkdir(parents=True,exist_ok=True)
def read(t,p):return store.request('GET',t,params={'select':'*',**p})[0]
project=read('std_projects',{'id':'eq.'+pid})[0]
assets=read('std_project_assets',{'project_id':'eq.'+pid,'status':'in.(uploaded,assigned)','order':'created_at.desc'})
job=next(a for a in assets if a['metadata'].get('kind')=='ae_mouth_job');meta=job['metadata'];snapshot=meta['input'];assert meta['state']=='review_pending'
results=meta['results'];completed={r['number']:r for r in results if r['status']=='review_pending'};assert set(completed)=={23,24,32,45,100}
(out/'input-snapshot.json').write_text(json.dumps({'project':project,'job':job,'assets':assets},ensure_ascii=False,indent=2),encoding='utf8')
dialogue=assess_dialogue(CodexStagedContentRunner(),meta['fingerprint'],snapshot)
notes=['# 토픽 3373 AE 오류·미완료 원인 및 현재 상태 최종 렌더', '',f'기록: {datetime.now().isoformat(timespec="seconds")}',f'프로젝트: `{pid}`',f'AE 작업: `{job["id"]}`','', '## 현재 판정','', '- 입모양 AE 영상 완성: 23, 24, 32, 45, 100씬 (5/16). 아직 사용자 개별 검수 완료 상태는 아님.', '- 53, 57, 59, 84씬: 화자·입 위치 불확실. 사용자가 명시적으로 제외 승인.', '- 63씬: 실제 대사 없음. 입모양 애니메이션 제외.', '', '## 현재 미완료 씬과 직접 원인', '', '| 씬 | 원인 | 관측된 수치 / 증거 |','|---|---|---|']
for row in results:
 if row['status']!='needs_review':continue
 scene=next(s for s in snapshot['scenes'] if s['number']==row['number'])
 bad=[r for r in dialogue if r['scene_number']==row['number'] and r['kind']=='dialogue' and not(0<=r['start']-scene['start']<r['end']-scene['start']<=scene['end']-scene['start']+.001)]
 evidence='; '.join(f'자막 {r["index"]}: 대사 {r["start"]:.6f}~{r["end"]:.6f}s / 씬 {scene["start"]:.6f}~{scene["end"]:.6f}s, 초과 {r["end"]-scene["end"]:.6f}s' for r in bad)
 reason='대사 구간이 씬 경계를 넘어서 진폭 기반 입모양 검증에서 보류' if bad else '생성 입 패치의 기존 입술 잔상·이중 입술로 시각 QA 실패'
 notes.append(f'| {row["number"]} | {reason} | {evidence or row.get("reason","")} |')
notes+=['','시간 오류는 확정 TTS를 변경한 것이 아니라, 대사 분석 결과의 구간과 씬 경계 간 불일치가 엄격한 범위 검사에 걸린 것입니다. 위 수치는 저장된 입력과 캐시된 분석 응답에서 계산했습니다. 원인이 반올림인지 실제 분할 문제인지 수치별로 구분해야 하며, 이번 작업에서는 임의로 음성을 잘라 검증을 우회하지 않습니다.','','## 앞서 발생했고 보완한 문제','','- 기존 제출 기록의 조기 반환으로 AE 큐 미등록 → 재제출 시 AE 등록·검증 후 중복 최종 제출 검사하도록 운영 배포.', '- 자막 임시 시간이 확정 TTS 시간과 불일치 → 대사·성우 일치를 검증한 뒤 기존 녹음 타임라인으로 복구.', '- Codex 이미지 옵션이 지침을 인자로 흡수해 stdin 입력 없음 → 지침 파일을 stdin으로 전달하도록 수정, 관련 테스트 통과.', '- AE 자동 복구용 pywinauto 누락 → 로컬 환경에 0.6.9 설치 및 import 검증.', '- 화면 3/16과 실제 서버 수 불일치 → 화면 원인은 로그인된 동일 화면에서 재현되지 않아 미확정. 실제 서버 최종값은 5/16.', '', '## 이번 렌더에서 명시적으로 적용하는 예외','','사용자 요청: “현재 오류나거나 작업안된 원인 파악해서 md파일로 기록해 놓고, 일단 이 상태에서 최종 렌더링을 해”. 따라서 이번 v4에 한해 미완료 AE를 기다리지 않고 현재 소스를 사용합니다. 기존 필수 AE·검수 규칙을 전역 변경하거나 실패 씬을 승인 완료로 표시하지 않습니다.','','- 1~18씬: 이전에 완성된 AE 출력 사용.', '- 23·24·32·45·100씬: 이번 완성된 입모양 AE 영상 사용. 녹음 구간 길이 고정, 루프·속도 변경 없음.', '- 나머지 19~101씬: 현재 플랫폼의 활성 원본 이미지 사용. 19씬 이후 새로 복구한 이미지 반영.', '- 미완료 11씬은 이번 렌더에서 입모양 AE 없이 원본 이미지 사용. 42씬의 이중 입술 패치는 사용하지 않음.', '- 현재 확정 TTS와 자막 시간·성우 유지. 새 음성 생성 없음.', '- 기존 v3 MP4 및 소스 보존. 새 디렉터리에 v4 생성.', '']
report=ROOT/'docs/AE_3373_current_state_render_20261005.md';report.parent.mkdir(exist_ok=True);report.write_text('\n'.join(notes),encoding='utf8');print('REPORT',report,flush=True)
old=ROOT/'_dev/artifacts/final_3373_ae_v3';config=json.loads((old/'config.json').read_text(encoding='utf-8-sig'))
image_dir=out/'images';image_dir.mkdir(exist_ok=True)
provenance=[]
def prepare(n):
 if n<=18:
  source=old/'images'/f'scene_{n:03}.mp4';target=image_dir/source.name;shutil.copy2(source,target);return target,{'scene':n,'source':'previous_ae_v3','path':str(source)}
 if n in completed:
  row=completed[n];a=next(a for a in assets if a['id']==row['asset_id']);m=a['metadata'];source=ROOT/'output/codex-local-console/ae-mouth'/meta['fingerprint']/f'scene-{n}'/'ae-mouth-preview.mp4'
  assert hashlib.sha256(source.read_bytes()).hexdigest()==row['render_sha256']==m['render_sha256'];target=image_dir/f'scene_{n:03}.mp4';shutil.copy2(source,target);return target,{'scene':n,'source':'ae_mouth_output','asset_id':a['id'],'sha256':row['render_sha256']}
 a=next(a for a in assets if a['asset_type']=='image' and a['scene_number']==n);m=a['metadata'];target=image_dir/f'scene_{n:03}.png'
 source=ROOT/'output/codex-local-console/image-repair-3373/generated'/f'scene-{n:03}'/'normalized.png'
 if m.get('image_repair_sha256') and source.exists() and hashlib.sha256(source.read_bytes()).hexdigest()==m['image_repair_sha256']:shutil.copy2(source,target)
 else:_download_gcs_file(GcsRef(m.get('gcs_bucket') or m.get('storage_bucket'),m.get('gcs_path') or m.get('storage_path')),target)
 return target,{'scene':n,'source':'current_image','asset_id':a['id'],'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
with ThreadPoolExecutor(max_workers=5) as pool:prepared=list(pool.map(prepare,range(1,102)))
audio=next(a for a in assets if a['id']==snapshot['audio']['id']);m=audio['metadata'];audio_path=out/'narration.mp3';_download_gcs_file(GcsRef(m.get('gcs_bucket') or m.get('storage_bucket'),m.get('gcs_path') or m.get('storage_path')),audio_path)
from services.remote_render_service import _probe_media_duration
audio_duration=_probe_media_duration(ffmpeg(),str(audio_path));assert audio_duration>0
starts=[0]+[s['start'] for s in snapshot['scenes']] # obtain all 101 starts from recorded subtitles below
timeline=audio['metadata']['subtitle_timeline'];subs=project['project_payload']['subtitles'];starts=[]
for n in range(1,102):
 indices=[i for i,r in enumerate(subs) if int(r.get('scene_number') or r.get('scene') or r.get('sceneNumber') or 0)==n]
 starts.append(timeline[indices[0]]['start'] if indices else None)
starts[0]=0
for i in range(1,101):
 if starts[i] is None:
  j=next((j for j in range(i+1,101) if starts[j] is not None),101);end=starts[j] if j<101 else audio_duration;left=i-1
  for k in range(i,j):starts[k]=starts[left]+(end-starts[left])*(k-left)/(j-left)
assert all(starts[i]<starts[i+1] for i in range(100))
durations=[(starts[i+1] if i<100 else audio_duration)-starts[i] for i in range(101)]
settings=copy.deepcopy(config['render_settings']);settings['timing_locked_indices']=[n-1 for n in completed]
for n in completed:
 scene=next(s for s in snapshot['scenes'] if s['number']==n);assert abs(durations[n-1]-(scene['end']-scene['start']))<=.12
config.update(images=[p[0].name for p in prepared],subtitles=subs,audio_filename=audio_path.name,audio_duration=audio_duration,image_timing_starts=starts,render_settings=settings,render_version=4,worker_tts={'enabled':False})
(out/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8');(out/'source-provenance.json').write_text(json.dumps([p[1] for p in prepared],ensure_ascii=False,indent=2),encoding='utf8')
overlay=old/'overlays/std_template_overlay.png'
def progress(percent,message):
 (out/'progress.txt').write_text(json.dumps({'progress':percent,'message':message},ensure_ascii=False),encoding='utf8');print(percent,message,flush=True)
print('RENDER_START',audio_duration,flush=True)
result=render_ffmpeg_slideshow(temp_dir=str(out),images=[str(p[0]) for p in prepared],audio_path=str(audio_path),durations=durations,subtitles=subs,subtitle_settings=settings,image_effects=['none']*101,transition_effects=['none']*101,resolution=(1920,1080),template_overlay_path=str(overlay) if overlay.exists() else None,use_gpu=True,progress_callback=progress,sfx_cues=[])
print('RENDER_DONE',result,flush=True)
