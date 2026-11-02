"""Run the bounded scene 19 repair with persistent logs and explicit status."""
import json, subprocess, time, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/codex-local-console/d57947df4af3479b85185c7ca0610a60/actual-production'
STATUS = OUT / 'scene19-repair-status.json'
def write(status, **extra):
    tmp = STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps({'status':status,'updated_at':time.time(),**extra}, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(STATUS)
task = '''Repair topic 3386 scene 19 only. Read AGENTS.md and imagegen skill. Existing scene image and planes and ownership must be preserved; do not perform face comparison. Use output/codex-local-console/d57947df4af3479b85185c7ca0610a60/actual-production/corrections/scene-019/composition-reference-v2.png as the corrected composition target (inspect it and scene 19 original). Generate genuinely independent background and transparent character planes using the built-in image_gen tool, preserving character identity and clear open palm, aligned with the composition, save under a NEW correction directory, composite and visually inspect all actual outputs. Do not claim a quality pass without real visual inspection. Identify actual web topic storage and usage path, and ONLY if topic 3386 is still pending, unassigned, not canceled and source is d57947df4af3479b85185c7ca0610a60 and its scene 19 assets have not changed, conditionally update scene 19 image and all corresponding independent plane references together, then re-fetch and verify. Do not modify other scenes or topics, publish administratively, render, or upload to YouTube. Never overwrite existing assets. If unable to update safely, save artifacts and report exact blocker. End with a concise factual report including paths, visual findings and whether DB was actually updated and verified.'''
try:
    write('running')
    result = subprocess.run(['codex','exec','--ephemeral','--skip-git-repo-check','--sandbox','workspace-write','--color','never','--json','-C',str(ROOT),'--output-last-message',str(OUT/'scene19-repair-result.txt'),task], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=3600)
    (OUT/'scene19-repair-events.jsonl').write_text(result.stdout,encoding='utf-8')
    (OUT/'scene19-repair-stderr.log').write_text(result.stderr,encoding='utf-8')
    write('finished' if result.returncode == 0 else 'failed', returncode=result.returncode)
except Exception as exc:
    write('failed',error=str(exc),traceback=traceback.format_exc())
