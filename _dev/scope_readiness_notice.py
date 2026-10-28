from pathlib import Path
import subprocess
root=Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip()
name='auth-web/components/StdTtsReadinessNotice.tsx'
current=Path(name).read_bytes()
base=subprocess.check_output(['git','-C',root,'show','HEAD:'+name])
start=current.index(b'    const sharedDescription')
end=current.index(b'    return <div',start)
base=base.replace(b'    return <div',current[start:end]+b'    return <div',1)
old="{ui('이 대사는 내레이션과 같은 성우({voice})를 사용합니다. 캐릭터에 맞는 다른 성우를 선택해 주세요.', {voice: voices.get(issue.voice) || issue.voice})}".encode()
assert old in base
base=base.replace(old,b'{sharedDescription(issue.voice, issue.narrationIndexes)}',1)
(Path(root)/name).write_bytes(base)
name='auth-web/tests/std-tts-readiness-notice.cjs'
base=subprocess.check_output(['git','-C',root,'show','HEAD:'+name])
current=Path(name).read_bytes()
base+=b'\n'+current[current.index(b'const mixedRows ='):]
(Path(root)/name).write_bytes(base)
