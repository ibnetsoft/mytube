import subprocess
from pathlib import Path
root=Path('_dev/artifacts/project_completion_release_root.txt').read_text().strip()
name='worker/local_media_supervisor.py'
data=subprocess.check_output(['git','-C',root,'show','HEAD:'+name])
new=Path(name).read_bytes()
helper=new[new.index(b'\ndef queue_poll_delay'):new.index(b'\ndef write_state')]
data=data.replace(b'\ndef write_state',helper+b'\ndef write_state',1)
for old,replacement in [
    (b'            write_state(self.state)\n            try:',b'            write_state(self.state)\n            queue_failures = 0\n            try:'),
    (b'                        roles=self.queue();role=self.choose(roles)',b'                        roles=self.queue();role=self.choose(roles)\n                        queue_failures = 0\n                        delay = queue_poll_delay(self.poll, idle=not roles)'),
    (b'                    except Exception as error:\n                        self.state.update',b'                    except Exception as error:\n                        queue_failures += 1\n                        delay = queue_poll_delay(self.poll, failures=queue_failures)\n                        self.state.update'),
    (b'                    self.stop.wait(self.poll)',b'                    self.stop.wait(delay)')]:
    if old not in data: old,replacement=old.replace(b'\n',b'\r\n'),replacement.replace(b'\n',b'\r\n')
    assert old in data
    data=data.replace(old,replacement,1)
(Path(root)/name).write_bytes(data)
