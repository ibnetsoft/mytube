import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
WORKER_DIR = ROOT / 'worker'
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import dashboard_app
import manager


def test_manager_always_on_child_scripts_includes_remote_drive_worker():
    assert 'remote_drive_worker' in manager.ALWAYS_ON_CHILD_SCRIPTS
    assert 'render_worker' in manager.ALWAYS_ON_CHILD_SCRIPTS
    assert 'local_api' in manager.ALWAYS_ON_CHILD_SCRIPTS


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
