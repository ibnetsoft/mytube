"""Exercise HTTP body parsing through the actual portable script entry point."""
import subprocess
import sys
from pathlib import Path


def test_portable_launch_resolves_postponed_request_models():
    root = Path(__file__).resolve().parents[1]
    probe = r'''
import re, sys
import uvicorn
from fastapi.testclient import TestClient

def verify(app, **kwargs):
    client = TestClient(app, base_url='http://127.0.0.1:3003')
    html = client.get('/').text
    token = re.search(r'name="local-token" content="([^"]+)"', html).group(1)
    headers = {'X-Codex-Local': token}
    response = client.post('/api/title-display', json={'items': []}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {'items': []}
    response = client.post('/api/jobs', json={}, headers=headers)
    assert response.status_code == 422, response.text
    print('portable request model validation passed')

uvicorn.run = verify
from worker.launch import main
sys.argv = ['worker.launch', '--role', 'script']
main()
'''
    result = subprocess.run([sys.executable, '-c', probe], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'portable request model validation passed' in result.stdout
