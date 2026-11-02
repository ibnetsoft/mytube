"""Supervise one authorized NEW job through real user-web topic registration."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'worker'))
import worker_config
from worker.script_worker_store import ScriptStore
from worker.script_topic_delivery import complete_candidate, publish_topic, write
from codex_content_runner import CodexStagedContentRunner


def local_job(identity):
    base = 'http://127.0.0.1:3003'
    html = urllib.request.urlopen(base, timeout=10).read().decode()
    token = re.search(r'name="local-token" content="([^"]+)"', html).group(1)
    return json.load(urllib.request.urlopen(urllib.request.Request(base+'/api/jobs/'+identity,
        headers={'X-Codex-Local': token}), timeout=30))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    parser.add_argument('--effect-start', type=int)
    parser.add_argument('--effect-end', type=int)
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{32}', args.job):
        raise ValueError('Exact existing job ID required')
    root = ROOT/'output/codex-local-console'/args.job
    directory = root/'delivery'
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory/'supervisor.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    if sys.platform == 'win32':
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    store = ScriptStore()
    request = json.loads((root/'request.json').read_text(encoding='utf-8'))
    if (args.effect_start is None) != (args.effect_end is None):
        raise ValueError('Both effect range bounds are required')
    effect_scope = None
    if args.effect_start is not None:
        if not 1 <= args.effect_start <= args.effect_end <= 999:
            raise ValueError('Invalid effect range')
        effect_scope = {'start': args.effect_start, 'end': args.effect_end}
    if request.get('mode') != 'new':
        raise ValueError('Existing topics and repair jobs are outside this supervisor scope')
    def notify(stage, **extra):
        write(directory/'status.json', {'source_job_id': args.job, 'stage': stage, 'updated_at': time.time(), **extra})
        print(stage, flush=True)
        if extra.get('status') != 'waiting' and (root/'candidate.json').exists():
            bundle = store.get(args.job)
            if bundle['job'].get('status') == 'canceled':
                raise ValueError('Source job canceled during delivery')
            if bundle['job'].get('status') not in ('queued', 'running', 'completed'):
                bundle['job'].update(stage=stage, updated_at=time.time(), delivery_supervised=True)
                store.save(bundle)
    retries = 0
    while True:
        try:
            try:
                data = local_job(args.job)
                job = data['job']
            except (OSError, TimeoutError):
                # The existing launcher only starts a missing server; it never
                # terminates a healthy worker or an unrelated listener.
                subprocess.run(['powershell', '-NoProfile', '-File', str(ROOT/'scripts/start_codex_local_console.ps1')],
                               cwd=ROOT, capture_output=True, timeout=40)
                job = store.get(args.job)['job']
            if job['status'] == 'canceled':
                notify('사용자 취소 · 종료', status='canceled'); return
            source_status = (job.get('delivery_source_status') or job['status']) if job.get('delivery_active') and job['status'] == 'running' else job['status']
            stored = store.get(args.job)
            has_candidate = bool(stored.get('candidate', {}).get('script') and stored.get('candidate', {}).get('structure', {}).get('scenes'))
            if source_status in ('queued', 'running') and not has_candidate:
                notify('대본 생성 대기 · '+job.get('stage', ''), status='waiting')
                time.sleep(30); continue
            if source_status in ('failed', 'interrupted') and not has_candidate:
                # Keep the SAME job directory/CLI artifact prefixes on recovery.
                # A separate runner does not restart or interrupt the live server.
                from worker.codex_local_workflow import produce
                retries += 1
                notify('저장된 단계에서 생성 복구', status='recovering', retry=retries)
                bundle = store.get(args.job)
                overrides = {'_effect_scope_override': effect_scope} if effect_scope else {}
                package = produce(args.job, {**request, '_delivery_quality_notes_only': True, **overrides}, None, root, notify)
                write(root/'candidate.json', package)
                bundle['candidate'] = package
                bundle['job'].update(status='awaiting_approval', stage='복구 생성 완료 · 주제 등록 준비')
                store.save(bundle)
            path = root/'candidate.json'
            if not path.exists():
                raise ValueError('Terminal job has no actual candidate artifact')
            candidate = json.loads(path.read_text(encoding='utf-8'))
            if effect_scope:
                candidate.setdefault('structure', {})['effect_scene_range'] = effect_scope
                candidate['structure']['skip_face_identity_review'] = True
            notify('대본 결과 확인 · 주제페이지 후속 준비', status='preparing')
            delivery_request = {**request, 'concentrated_scene_effects': True, 'image_layer_scene_start': effect_scope['start'], 'image_layer_scene_end': effect_scope['end']} if effect_scope else request
            package = complete_candidate(args.job, candidate, delivery_request, CodexStagedContentRunner(), directory, notify)
            # Scene-level translations use the same local Codex worker as subtitle
            # review and are tied to the exact narration, never a stale draft.
            from worker.codex_subtitle_translation import translate_blocks
            script_hash = hashlib.sha256(package['script'].encode('utf-8')).hexdigest()
            scenes = package['structure']['scenes']
            blocks = [{'index': i, 'source_text': str(s.get('scene_text') or s.get('narration') or '').strip()}
                      for i, s in enumerate(scenes)]
            if not blocks or any(not b['source_text'] for b in blocks) or '\n\n'.join(b['source_text'] for b in blocks) != package['script']:
                raise ValueError('최종 씬과 대본이 일치하지 않아 번역을 저장할 수 없습니다.')
            translations = {}
            for language in (('ko', 'th') if request.get('language') != 'ko' else ('th',)):
                notify('대본 번역 · ' + language, status='preparing')
                target = directory / ('script-translation-' + language + '-' + script_hash + '.json')
                legacy = directory / ('script-translation-' + language + '.json')
                cached_path = target if target.exists() else legacy
                cached = json.loads(cached_path.read_text(encoding='utf-8')) if cached_path.exists() else {}
                result = cached or None
                if result and (result.get('source_script_sha256') != script_hash or
                               result.get('target_language') != language or
                               [b.get('index') for b in result.get('blocks', [])] != [b['index'] for b in blocks] or
                               [b.get('source_text') for b in result.get('blocks', [])] != [b['source_text'] for b in blocks] or
                               any(not str(b.get('translated_text') or '').strip() for b in result.get('blocks', []))):
                    result = None
                if not result:
                    previous = {b.get('index'): b for b in cached.get('blocks', []) if isinstance(b, dict)} if cached.get('target_language') == language else {}
                    reusable = {b['index']: previous[b['index']] for b in blocks
                                if b['index'] in previous and previous[b['index']].get('source_text') == b['source_text']
                                and str(previous[b['index']].get('translated_text') or '').strip()}
                    missing = [b for b in blocks if b['index'] not in reusable]
                    fresh = translate_blocks(CodexStagedContentRunner(), args.job + '-' + language, missing, language) if missing else []
                    translated = {b['index']: b for b in fresh}
                    translated.update(reusable)
                    result = {'version': 1, 'source_script_sha256': script_hash,
                              'source_language': request.get('language'), 'target_language': language,
                              'scope': 'scene_narration',
                              'blocks': [translated[b['index']] for b in blocks],
                              'updated_at': time.time()}
                    write(target, result)
                translations[language] = result
            package['script_translations'] = translations
            package.setdefault('remaining', []).append('최종 자막 블록별 번역 연결 및 검증')
            notify('유저웹 주제 등록·실제 읽기 검증', status='registering')
            receipt = publish_topic(args.job, package, request, store, directory)
            package['remaining'] = [item for item in package.get('remaining', [])
                                    if not str(item).startswith('토픽 패키지/유저웹 연결')]
            bundle = store.get(args.job)
            # Publish only the new, explicitly authorized source job record.
            bundle['job'].update(published=True, topic_queue_id=receipt['topic_id'],
                status='approved_pending_repair', stage='유저웹 등록 · 실제 이미지 및 자막 연결 준비 대기', updated_at=time.time(),
                remaining=package.get('remaining', []),
                quality_notes_path=str(directory/'quality-notes.json'))
            write(directory/'quality-notes.json', {'script_quality_report': package.get('script_quality_report'),
                'quality_notes': package.get('structure', {}).get('quality_notes', []),
                'actual_images_generated': False, 'ae_render_complete': False,
                'registration_scope': 'Reviewed script, scene prompts, layer/AE plans, BGM/SFX and metadata; actual media remains downstream.'})
            bundle['candidate'] = package
            store.save(bundle)
            write(root/'job.json', bundle['job'])
            write(root/'candidate.json', package)
            notify('유저웹 주제페이지 등록 완료', status='completed', **receipt)
            return
        except Exception as error:
            try:
                if store.get(args.job)['job'].get('status') == 'canceled':
                    write(directory/'status.json', {'source_job_id': args.job, 'status': 'canceled', 'stage': '사용자 취소 · 종료'})
                    return
            except Exception:
                pass  # A database outage must not terminate the recovery loop.
            write(directory/'last-error.json', {'type': type(error).__name__, 'message': str(error),
                'traceback': traceback.format_exc(), 'updated_at': time.time()})
            # Long provider outages remain retryable without losing any successful
            # stage. Contract failures are surfaced for actual repair, not approved.
            retries += 1
            delay = min(300, 20 * 2**min(retries, 4))
            write(directory/'status.json', {'source_job_id': args.job,
                'stage': '오류 기록 · 저장 단계 보존 후 복구 대기', 'status': 'retry_wait',
                'error_type': type(error).__name__, 'retry': retries, 'retry_after': time.time()+delay})
            time.sleep(delay)


if __name__ == '__main__':
    main()
