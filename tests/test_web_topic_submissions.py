import copy
import uuid
import pytest
from fastapi.testclient import TestClient
from worker import codex_local_console as console
from worker.web_topic_submissions import prepare_brief, review_submission, generation_request


class QueueStore:
    def __init__(self):
        self.row = {'id': str(uuid.uuid4()), 'status': 'pending', 'title': '새 이야기',
            'request_data': dict(title='새 이야기', story='결말을 바꾼다', category='옛날이야기',
                duration_minutes=15, language='ko', setting_country='한국', era_region='현대',
                image_style='실사', production_mode='standard', character_images=[])}
        self.active_rows = []

    def request(self, method, table, **kwargs):
        if method == 'GET':
            return [copy.deepcopy(self.row)], 1
        if self.row['status'] != 'pending':
            return [], 0
        self.row.update(kwargs['body'])
        return [copy.deepcopy(self.row)], 1

    def active(self):
        return self.active_rows


def test_only_first_review_claims():
    store = QueueStore()
    claimed = review_submission(store, store.row['id'], 'approved', '')
    assert claimed['job_id'] == uuid.UUID(store.row['id']).hex
    with pytest.raises(ValueError):
        review_submission(store, store.row['id'], 'approved', '')


def test_web_request_preserves_brief():
    store = QueueStore()
    request = console.StartRequest.model_validate(generation_request(store.row))
    assert request.mode == 'new'
    assert request.web_brief['story'] == '결말을 바꾼다'
    assert request.web_topic_id == store.row['id']
    assert request.ae_scene_delivery == 'gcs'


@pytest.mark.parametrize('language,name', [('ko', 'Korean'), ('ja', 'Japanese'), ('en', 'English')])
@pytest.mark.parametrize('input_language,story', [('th', 'หญิงสาวพบจดหมายเก่า'), ('vi', 'Cô gái tìm thấy một bức thư cũ')])
def test_multilingual_brief_keeps_selected_output_language(tmp_path, language, name, input_language, story):
    row = QueueStore().row
    row['request_data'].update(language=language, input_language=input_language, story=story)
    request = console.StartRequest.model_validate(generation_request(row)).model_dump()
    notes = prepare_brief(request, tmp_path, None, lambda message: None)
    assert request['language'] == language
    assert request['web_brief']['story'] == story
    assert story in notes
    assert f'OUTPUT LANGUAGE: {name} ({language})' in notes
    assert f'Input language hint: {input_language}' in notes


def test_ae_scene_delivery_reaches_local_candidate(monkeypatch, tmp_path):
    from worker import codex_local_workflow as workflow
    from worker import codex_bgm
    import codex_content_runner

    row = QueueStore().row
    row['request_data']['ae_scene_delivery'] = 'gcs'
    request = console.StartRequest.model_validate(generation_request(row)).model_dump()
    captured = {}

    monkeypatch.setattr(codex_content_runner.CodexContentConfig, 'from_environment',
                        classmethod(lambda cls: object()))
    def fake_generate(self, identity, payload, *, script_only):
        captured.update(payload)
        assert script_only is True
        return {'script': '대본', 'structure': {'scenes': []}}
    monkeypatch.setattr(codex_content_runner.CodexStagedContentRunner, 'generate', fake_generate)
    monkeypatch.setattr(codex_bgm, 'plan_package_bgm', lambda *args, **kwargs: None)
    monkeypatch.setattr(workflow, 'finalize_sfx', lambda _runner, _identity, package, _notify, _source=None: package)

    package = workflow.produce('job', request, None, tmp_path, lambda _stage: None)
    assert captured['ae_scene_delivery'] == 'gcs'
    assert package['ae_scene_delivery'] == 'gcs'
    assert package['structure']['ae_scene_delivery'] == 'gcs'
    assert package['render_settings']['ae_scene_delivery'] == 'gcs'


def test_invalid_ae_scene_delivery_is_rejected():
    row = QueueStore().row
    row['request_data']['ae_scene_delivery'] = 'remote-shell'
    with pytest.raises(ValueError, match='AE 씬 영상 전달 방식'):
        generation_request(row)


def test_routes_require_local_token_and_approval(monkeypatch, tmp_path):
    store = QueueStore()
    jobs = console.Jobs(tmp_path)
    calls = []
    monkeypatch.setattr(console, 'store', store)
    monkeypatch.setattr(console, 'jobs', jobs)
    monkeypatch.setattr(jobs, 'start', lambda request, snapshot, **kwargs: calls.append(request) or {'id': kwargs['identity']})
    client = TestClient(console.app, base_url=console.ORIGIN)
    path = '/api/web-topics/' + store.row['id'] + '/review'
    assert client.post(path, json={'action': 'approve'}).status_code == 401
    headers = {'X-Codex-Local': console.TOKEN}
    assert client.get('/api/web-topics', headers=headers).status_code == 200
    assert not calls
    store.active_rows = [{'id': 'busy'}]
    assert client.post(path, headers=headers, json={'action': 'approve'}).status_code == 409
    assert store.row['status'] == 'pending'
    store.active_rows = []
    assert client.post(path, headers=headers, json={'action': 'approve'}).status_code == 200
    assert len(calls) == 1
    assert client.post(path, headers=headers, json={'action': 'approve'}).status_code == 409
    assert len(calls) == 1


def test_reject_never_starts(monkeypatch, tmp_path):
    store = QueueStore()
    monkeypatch.setattr(console, 'store', store)
    monkeypatch.setattr(console, 'jobs', console.Jobs(tmp_path))
    client = TestClient(console.app, base_url=console.ORIGIN)
    path = '/api/web-topics/' + store.row['id'] + '/review'
    headers = {'X-Codex-Local': console.TOKEN}
    assert client.post(path, headers=headers, json={'action': 'reject'}).status_code == 409
    assert client.post(path, headers=headers, json={'action': 'reject', 'note': '줄거리 보완'}).status_code == 200
    assert store.row['status'] == 'rejected'
    assert store.row['job_id'] is None


def test_reference_analysis_is_used_and_transcript_failure_stops(monkeypatch, tmp_path):
    class Runner:
        def _stage(self, *args):
            return {'summary': '영상의 중심 갈등'}
    request = generation_request(QueueStore().row)
    request['web_brief'].update(transcript='참고 자료 원문', character_notes='조용한 주인공')
    notes = prepare_brief(request, tmp_path, Runner(), lambda s: None)
    assert '영상의 중심 갈등' in notes and '조용한 주인공' in notes
    request['web_brief'].update(transcript='', youtube_url='https://youtu.be/abcdefghijk')
    from worker import youtube_transcript
    def fail(url):
        raise RuntimeError('no captions')
    monkeypatch.setattr(youtube_transcript, 'extract_transcript', fail)
    with pytest.raises(RuntimeError, match='유튜브 자막 수집 실패'):
        prepare_brief(request, tmp_path, Runner(), lambda s: None)


def test_character_images_are_attached_to_analysis(tmp_path):
    import base64
    request = generation_request(QueueStore().row)
    request['web_brief']['character_images'] = [{'name': 'hero.png', 'data': 'data:image/png;base64,' + base64.b64encode(b'example-image').decode()}]
    class Runner:
        def _stage(self, identity, name, context, task):
            assert name == '02_character_reference_analysis'
            from pathlib import Path
            assert Path(context['_local_image_paths'][0]).read_bytes() == b'example-image'
            return {'description': '붉은 옷을 입은 인물'}
    assert '붉은 옷' in prepare_brief(request, tmp_path, Runner(), lambda s: None)


def test_retry_link_only_advances_matching_submission(monkeypatch):
    from worker.script_worker_store import ScriptStore
    store = ScriptStore()
    calls = []
    monkeypatch.setattr(store, 'request', lambda *args, **kwargs: calls.append((args, kwargs)))
    old, new = uuid.uuid4().hex, uuid.uuid4().hex
    topic_id = str(uuid.uuid4())
    store.save({'job': {'id': new, 'title': '재실행', 'mode': 'new', 'status': 'queued',
        'created_at': 1, 'updated_at': 1, 'retry_of': old}, 'request': {'web_topic_id': topic_id}})
    args, kwargs = calls[-1]
    assert args == ('PATCH', 'user_topic_submissions')
    assert kwargs['params']['id'] == 'eq.' + topic_id
    assert kwargs['params']['job_id'] == f'in.({new},{old})'
    assert kwargs['body']['job_id'] == new
