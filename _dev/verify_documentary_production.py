"""Read public production HTML and its route scripts; never use session secrets."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
import requests

origin = 'https://studio.airing.work'
response = requests.get(origin + '/std', headers={'Cache-Control': 'no-cache'}, timeout=30)
response.raise_for_status()
paths = re.findall(r'<script[^>]+src="([^"]+)"', response.text)
paths = [path for path in paths if path.startswith('/_next/static/')]
def read(path):
    fetched = requests.get(origin + path, timeout=30)
    fetched.raise_for_status()
    return fetched.text
with ThreadPoolExecutor(max_workers=4) as pool:
    scripts = '\n'.join(pool.map(read, paths))
checks = {marker: marker in scripts for marker in ('historical_source_notes', 'sumi_e_ukiyo_e')}
result = {'url': origin + '/std', 'status': response.status_code, 'script_count': len(paths), 'checks': checks}
print(json.dumps(result))
if not all(checks.values()):
    raise SystemExit(1)
