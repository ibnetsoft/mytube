"""Package only this task's unstaged hunks; preserve all other workspace work."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = [
    'auth-web/components/TopicSubmissionPanel.tsx', 'auth-web/lib/topicSubmission.ts',
    'auth-web/tests/topic-submissions.cjs', 'worker/japanese_historical_documentary.py',
    'tests/test_japanese_historical_documentary.py', 'worker/codex_local_console.py',
    'worker/codex_local_workflow.py', 'worker/web_topic_submissions.py',
]
chunks = []
for name in files:
    chunks.append(subprocess.check_output(['git', 'diff', '--', name], cwd=ROOT).decode('utf-8'))
runner = subprocess.check_output(['git', 'diff', '--', 'worker/codex_content_runner.py'], cwd=ROOT).decode('utf-8')
parts = re.split(r'(?=^@@ )', runner, flags=re.M)
selected = []
for part in parts[1:]:
    additions = '\n'.join(line for line in part.splitlines() if line.startswith('+'))
    if any(token in additions for token in ('documentary', 'historical_sources', 'prepare_sources', 'Historical evidence')):
        selected.append(part)
assert len(selected) == 8, len(selected)
chunks.append(parts[0] + ''.join(selected))
out = ROOT / '_dev/artifacts/documentary-readiness.patch'
out.write_text(''.join(chunks), encoding='utf-8', newline='\n')
print(out)
print('runner_hunks', len(selected))
