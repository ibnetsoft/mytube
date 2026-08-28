import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / 'worker'
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import dashboard_app
import manager
import worker_config


def test_manager_default_profile_starts_all_child_scripts():
    assert worker_config.WORKER_PROFILE == 'full'
    assert 'remote_drive_worker' in manager.ALWAYS_ON_CHILD_SCRIPTS
    assert 'render_worker' in manager.ALWAYS_ON_CHILD_SCRIPTS
    assert 'hermes_worker' in manager.ALWAYS_ON_CHILD_SCRIPTS
    assert 'local_api' in manager.ALWAYS_ON_CHILD_SCRIPTS


def test_worker_profiles_split_generation_and_rendering_roles():
    assert worker_config.normalize_worker_profile('content-only') == 'content_only'
    assert worker_config.normalize_worker_profile('render') == 'render_only'
    assert worker_config.normalize_worker_profile('script_only') == 'content_only'
    assert worker_config.normalize_worker_profile('bad-value') == 'full'
    assert worker_config.PROFILE_CHILD_SCRIPTS['full'] == (
        'render_worker',
        'remote_drive_worker',
        'hermes_worker',
        'local_api',
    )
    assert worker_config.PROFILE_CHILD_SCRIPTS['content_only'] == ('hermes_worker', 'local_api')
    assert worker_config.PROFILE_CHILD_SCRIPTS['render_only'] == ('render_worker', 'remote_drive_worker', 'local_api')


def test_entrypoint_supports_split_worker_roles():
    source = (WORKER_DIR / 'air_worker_entry.py').read_text(encoding='utf-8')

    assert '"render_worker"' in source
    assert '"remote_drive_worker"' in source
    assert 'import render_worker as mod' in source
    assert 'import remote_drive_worker_process as mod' in source
    assert '--profile' in source


def test_api_rendering_jobs_endpoint_returns_combined_queue_structure():
    client = TestClient(dashboard_app.app)
    response = client.get('/api/rendering-jobs?limit=10')
    assert response.status_code == 200
    data = response.json()
    assert 'jobs' in data
    assert 'active_job' in data
    assert 'active_count' in data
    assert 'pending_count' in data
    assert 'total_count' in data
    assert isinstance(data['jobs'], list)
