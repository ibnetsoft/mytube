"""Continue 3386 scene imagery after the real character-reference preflight."""
import json, sys, time, traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker import cowork_scene_assets as assets, image_recovery
from worker.script_worker_store import ScriptStore
from worker.script_topic_delivery import write
from codex_content_runner import CodexStagedContentRunner
import scripts.finish_user_topic_images as previous

ID='d57947df4af3479b85185c7ca0610a60'
OUT=ROOT/'output/codex-local-console'/ID/'actual-production'
MANIFEST=OUT/'manifest.json'; IMAGES=OUT/'images'
previous.JOB=ID; previous.BASE=OUT; previous.ART=OUT
runner=CodexStagedContentRunner()

def status(stage,state='running',**extra):
    write(OUT/'image-status.json',{'status':state,'stage':stage,'updated_at':time.time(),**extra})
def check_topic():
    rows,_=ScriptStore().request('GET','topics_queue',params={'id':'eq.3386','select':'*'})
    if len(rows)!=1:raise ValueError('토픽을 찾지 못했습니다.')
    row=rows[0];structure=row.get('pregenerated_structure') or {}
    if row.get('status')!='pending' or row.get('assigned_at') or row.get('assigned_employee_email'):
        raise ValueError('토픽이 배정 또는 취소되어 중복 제작을 중단합니다.')
    if (row.get('progress_payload') or {}).get('source_script_job_id')!=ID:
        raise ValueError('토픽 출처가 변경됐습니다.')
    if structure.get('effect_scene_range')!={'start':19,'end':50}:
        raise ValueError('확인된 효과 씬 범위가 변경됐습니다.')
    return row,structure
try:
    while not MANIFEST.exists():
        check_topic();status('캐릭터 참조 생성·얼굴 구별 확인 대기')
        # Do not launch a duplicate preflight. A stopped one needs inspection.
        import subprocess
        proc=subprocess.run(['powershell','-NoProfile','-Command',
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'prepare_3386_manifest.py' } | Select-Object -ExpandProperty ProcessId"],
            capture_output=True,text=True,timeout=15)
        if not proc.stdout.strip():raise RuntimeError('캐릭터 참조 준비 프로세스가 중단됐습니다. 로그를 확인하세요.')
        time.sleep(20)
    manifest=assets._manifest(MANIFEST)
    if manifest.get('effect_scene_range')!={'start':19,'end':50} or manifest.get('scene_count')!=104:
        raise ValueError('매니페스트 씬 수 또는 효과 범위 불일치')
    check_topic();image_recovery.ensure_state(MANIFEST); recovery=image_recovery.state_path(MANIFEST)
    while True:
        state=json.loads(recovery.read_text(encoding='utf-8')); summary=image_recovery.summary(state)
        if summary['complete']:break
        if summary['attention']:raise RuntimeError('이미지 작업 확인 필요: '+json.dumps(summary['attention'],ensure_ascii=False))
        jobs=summary['runnable']
        if not jobs:time.sleep(5);continue
        check_topic(); job=jobs[0]
        status('고정 이미지 생성',ready_grids=len(summary['ready']),job_id=job['id'])
        image_recovery.update_file(recovery,lambda s:image_recovery.transition(s,{'action':'start','job_id':job['id']}))
        try:
            image=previous.grid(job)
            image_recovery.update_file(recovery,lambda s:image_recovery.transition(s,{'action':'result','job_id':job['id'],
                'outcome':'generated','image_file':str(image)}))
            # A real image is passed to the local visual reviewer; never claim a visual review from a file check.
            image=Path(image).resolve()
            if not image.is_relative_to((ROOT/'output/codex-local-console').resolve()):
                import shutil
                local=OUT/'review-inputs'/f"{job['id']}.png";local.parent.mkdir(parents=True,exist_ok=True)
                if not local.exists():shutil.copyfile(image,local)
                image=local
            review=runner._stage('image-review-3386',job['id'],{'_local_image_paths':[str(image)],
                'scene_specs':job.get('scene_specs',[]),'scene_numbers':job['scene_numbers']},
                'Inspect the ACTUAL attached image for layout, relevant character identity and scene fidelity. '
                'Return JSON {verdict:"pass|needs_review",evidence:[specific observed facts],issues:[...]}. '
                'Never claim inspection if image unavailable. Do not rewrite the image.')
            if review.get('verdict') not in ('pass','needs_review') or not review.get('evidence'):
                raise ValueError('실제 이미지 시각 검토 결과가 불완전합니다.')
            write(OUT/'reviews'/f"{job['id']}.json",review)
            # Quality findings are retained as notes; generated asset is not falsely marked as visually passed.
            image_recovery.update_file(recovery,lambda s:image_recovery.transition(s,{'action':'accept','job_id':job['id'],
                'visual_review':json.dumps(review,ensure_ascii=False)}))
        except Exception as exc:
            state=json.loads(recovery.read_text(encoding='utf-8'));current=image_recovery.get_job(state,job['id'])
            if current.get('status')=='running':
                image_recovery.update_file(recovery,lambda s:image_recovery.transition(s,{'action':'result','job_id':job['id'],
                    'outcome':'unknown','reason':str(exc)}))
            raise
    check_topic();status('19~50씬 독립 레이어 및 씬 합성 생성')
    assets.crop_grids(MANIFEST,OUT/'native-grids',IMAGES)
    check_topic();status('실제 씬 이미지·레이어 저장')
    urls=assets.publish(MANIFEST,IMAGES,False,reuse_existing=True)
    if len(urls)!=104:raise ValueError(f'저장된 씬 이미지 수 불일치: {len(urls)}')
    _,structure=check_topic();saved=structure['scenes']
    ready=sum(bool(s.get('image_url') and s.get('asset_status')=='ready') for s in saved)
    layers=sum(bool(((s.get('metadata') or {}).get('cowork_image_asset') or {}).get('independent_planes')) for s in saved[18:50])
    if ready!=104 or layers!=32:raise ValueError(f'재조회 결과 씬 {ready}/104, 레이어 {layers}/32')
    status('실제 이미지·독립 레이어 저장 및 재조회 완료','completed',scene_images=ready,layer_scenes=layers)
except Exception as exc:
    write(OUT/'image-error.json',{'message':str(exc),'traceback':traceback.format_exc(),'updated_at':time.time()})
    status('이미지 작업 중단','failed',error=str(exc))
