import difflib,subprocess
from pathlib import Path
root=Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip()
for name in ['worker/motion_automation_worker.py','worker/effectcraft_render.py','auth-web/lib/stdMotionAutomation.ts','auth-web/components/StdMotionAutomation.tsx','auth-web/app/api/std/projects/[projectId]/motion-automation/route.ts','auth-web/tests/std-motion-automation.cjs']:
    original=subprocess.check_output(['git','-C',root,'show','HEAD:'+name]).decode('utf-8').splitlines(keepends=True)
    file=Path(root)/name
    current=file.read_bytes().decode('utf-8').splitlines(keepends=True)
    matcher=difflib.SequenceMatcher(None,[x.rstrip('\r\n') for x in original],[x.rstrip('\r\n') for x in current],autojunk=False)
    output=[]
    for kind,a,b,c,d in matcher.get_opcodes():output.extend(original[a:b] if kind=='equal' else current[c:d])
    file.write_bytes(''.join(output).encode('utf-8'))
