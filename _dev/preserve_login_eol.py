import difflib, subprocess
from pathlib import Path
root = Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip()
name = 'auth-web/app/std/page.tsx'
original = subprocess.check_output(['git', '-C', root, 'show', 'HEAD:' + name]).decode().splitlines(keepends=True)
file = Path(root) / name
current = file.read_bytes().decode().splitlines(keepends=True)
matcher = difflib.SequenceMatcher(None, [x.rstrip('\r\n') for x in original], [x.rstrip('\r\n') for x in current], autojunk=False)
output = []
for kind, a, b, c, d in matcher.get_opcodes():
    output.extend(original[a:b] if kind == 'equal' else current[c:d])
file.write_bytes(''.join(output).encode())
