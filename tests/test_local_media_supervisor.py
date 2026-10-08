from pathlib import Path
import pytest
from worker import local_media_supervisor as media
from scripts.build_script_worker_bundle import build
import zipfile

@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(media, 'HOME', tmp_path/'state')
    monkeypatch.setattr(media, 'LOGS', tmp_path/'logs')
    monkeypatch.setattr(media, 'busy_processes', lambda: [])
    return tmp_path

def test_no_overlapping_children_and_alternating_roles(isolated):
    running = []
    order = []
    class Child:
        pid = 123
        returncode = 0
        def poll(self):
            running.clear()
            return self.returncode
    def spawn(command, **kwargs):
        assert not running, 'AE and render must never overlap'
        running.append(command)
        order.append(command)
        return Child()
    manager = media.Supervisor(spawn=spawn)
    manager.execute(manager.choose(['ae','render']))
    manager.execute(manager.choose(['ae','render']))
    assert 'ae_mouth_worker.py' in order[0][2]
    assert 'remote_render_source.py' in order[1][2]

def test_three_failures_block_role_and_render_pause_is_preserved(isolated):
    manager = media.Supervisor()
    manager.failures['ae'] = 3
    assert manager.choose(['ae','render']) == 'render'
    media.HOME.mkdir()
    (media.HOME/'pause-render').touch()
    assert manager.choose(['ae','render']) is None

def test_region_jobs_use_separate_serialized_worker(isolated):
    assert media.role_command('region')[2].endswith('ae_region_motion_worker.py')
    manager = media.Supervisor()
    assert manager.choose(['region', 'render']) == 'region'
    manager.last_role = 'region'
    assert manager.choose(['region', 'render']) == 'render'

def test_ready_region_video_still_requires_review():
    from worker.local_media_dashboard import summarize
    assert summarize({'id':'r','scene_number':13,'metadata':{'kind':'region_motion_plan','state':'ready'}})['group'] == 'review'

def test_singleton_rejects_second_manager(isolated):
    with media.singleton():
        with pytest.raises(RuntimeError, match='already running'):
            with media.singleton(): pass

def test_archive_excludes_credentials_and_assets(tmp_path):
    root=tmp_path/'source'
    (root/'worker').mkdir(parents=True)
    for name in ['launch.py','connection.env','.env','auth.json','credential.pem','settings.json']:
        (root/'worker'/name).write_text('test', encoding='utf-8')
    (root/'worker/output').mkdir()
    (root/'worker/output/private.py').write_text('secret', encoding='utf-8')
    archive=tmp_path/'bundle.zip'
    build(archive,root)
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {'worker/launch.py','bundle-manifest.json'}

def test_dashboard_does_not_count_discovery_as_completed():
    from worker.local_media_dashboard import summarize
    job = summarize({'id':'job', 'metadata':{'kind':'ae_mouth_job','state':'review_pending',
        'input':{'scenes':[{}, {}, {}]}, 'results':[
            {'status':'direction_pending'}, {'status':'review_pending'}, {'status':'skipped'}],
        'secret':'private-key'}})
    assert job['group'] == 'review'
    assert job['done'] == 1 and job['analyzed'] == 3
    assert 'metadata' not in job and 'secret' not in job

def test_dashboard_preserves_last_snapshot_on_connection_failure(monkeypatch):
    from worker import local_media_dashboard as dashboard
    snapshot = dashboard.Snapshot()
    monkeypatch.setattr(dashboard, 'fetch_jobs', lambda: [{'id':'existing'}])
    first = snapshot.read()
    snapshot.next_poll = 0
    def fail(): raise TimeoutError('secret connection string')
    monkeypatch.setattr(dashboard, 'fetch_jobs', fail)
    failed = snapshot.read()
    assert failed['jobs'] == first['jobs']
    assert failed['updated_at'] == first['updated_at']
    assert failed['error'] == 'TimeoutError'
