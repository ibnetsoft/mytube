"""Local Codex chat, serialized through the script worker's existing execution pool."""
import json, os, re, shutil, subprocess, threading, time
from pathlib import Path

class LocalChat:
    def __init__(self, root, workspace, pool):
        self.root=Path(root); self.workspace=Path(workspace); self.pool=pool
        self.path=self.root/'chat'/'conversation.json'; self.lock=threading.RLock()
        self.data={'thread_id':None,'messages':[],'state':'idle','error':''}
        if self.path.exists():
            try: self.data=json.loads(self.path.read_text(encoding='utf-8'))
            except (OSError,ValueError): pass
        if self.data.get('state') in ('queued','running'):
            self.data.update(state='interrupted',error='워커가 종료되어 응답이 중단되었습니다. 다시 보내 주세요.')
            self.save()
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.data,ensure_ascii=False),encoding='utf-8');temp.replace(self.path)
    def snapshot(self):
        with self.lock: return json.loads(json.dumps(self.data,ensure_ascii=False))
    def reset(self):
        with self.lock:
            if self.data['state'] in ('queued','running'): raise ValueError('응답이 끝난 뒤 새 대화를 시작하세요.')
            self.data={'thread_id':None,'messages':[],'state':'idle','error':''};self.save();return self.snapshot()
    def send(self,message):
        message=message.strip()
        if not message or len(message)>12000: raise ValueError('메시지는 1~12,000자여야 합니다.')
        with self.lock:
            if self.data['state'] in ('queued','running'): raise ValueError('현재 응답이 끝난 뒤 보내 주세요.')
            self.data['messages'].append({'role':'user','text':message,'at':time.time()})
            self.data.update(state='queued',error='');self.save();self.pool.submit(self.run,message)
            return self.snapshot()
    def run(self,message):
        with self.lock:
            self.data['state']='running';self.save();thread_id=self.data.get('thread_id')
        try:
            executable=os.environ.get('CODEX_EXECUTABLE','codex').strip() or 'codex'
            executable=shutil.which(executable) or executable
            command=[executable,'--ask-for-approval','never','exec','--sandbox','workspace-write','--color','never','-C',str(self.workspace),'--json']
            if thread_id:
                if not re.fullmatch(r'[a-fA-F0-9-]{36}',thread_id): raise ValueError('저장된 대화 ID가 올바르지 않습니다.')
                command+=['resume',thread_id]
            command+=['-']
            result=subprocess.run(command,input=message,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=str(self.workspace),timeout=900,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            output=[];failed=False;new_thread=thread_id
            for line in result.stdout.splitlines():
                try: event=json.loads(line)
                except ValueError: continue
                if event.get('type')=='thread.started': new_thread=event.get('thread_id') or new_thread
                if event.get('type') in ('turn.failed','error'): failed=True
                item=event.get('item') or {}
                if event.get('type')=='item.completed' and item.get('type')=='agent_message': output.append(str(item.get('text') or ''))
            if result.returncode or failed or not output: raise RuntimeError('Codex 응답을 완료하지 못했습니다. CLI 로그인과 사용 가능 상태를 확인하세요.')
            with self.lock:
                self.data['thread_id']=new_thread;self.data['messages'].append({'role':'assistant','text':'\n\n'.join(output),'at':time.time()});self.data.update(state='idle',error='');self.save()
        except Exception as exc:
            with self.lock:
                self.data.update(state='failed',error=str(exc) if isinstance(exc,ValueError) else 'Codex 응답에 실패했습니다. CLI 로그인 및 워커 상태를 확인하고 다시 시도해 주세요.');self.save()
