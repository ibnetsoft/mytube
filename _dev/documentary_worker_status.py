"""Read local status without displaying the loopback session token."""
import json
import re
import sys
import requests

origin = 'http://127.0.0.1:3003'
html = requests.get(origin + '/', timeout=10).text
token = re.search(r'<meta name="local-token" content="([^"]+)"', html).group(1)
response = requests.get(origin + '/api/status', headers={'X-Codex-Local': token}, timeout=20)
response.raise_for_status()
status = response.json()
jobs = status.get('jobs') or []
summary = {'jobs_type': type(jobs).__name__, 'active': [
    {k: row.get(k) for k in ('id', 'status', 'title')} for row in jobs
    if isinstance(row, dict) and row.get('status') in ('running', 'queued')
], 'storage_connected': status.get('storage', {}).get('connected')}
print(json.dumps(summary, ensure_ascii=True))
if '--require-idle' in sys.argv and (summary['active'] or not summary['storage_connected']):
    raise SystemExit(1)
