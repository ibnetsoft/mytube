from pathlib import Path
roots=[Path.cwd(),Path(Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip())]
for root in roots:
    for name in ['StdMotionAutomation','StdMouthPreviews','StdLipSyncPanel']:
        path=root/f'auth-web/components/{name}.tsx'
        lines=path.read_bytes().splitlines(keepends=True)
        seen=False; output=[]
        for line in lines:
            if b"import { startVisiblePolling }" in line:
                if seen: continue
                seen=True
            output.append(line)
        path.write_bytes(b''.join(output))
