"""Post-submission AE, review and final rendering only; heavy jobs never overlap."""
from __future__ import annotations
import argparse, contextlib, json, os, signal, subprocess, sys, threading, time
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'worker'))
import worker_config
from ae_mouth_runtime import claimable_filter
HOME = worker_config.STATE_DIR / 'local-media'
LOGS = worker_config.LOG_DIR / 'local-media'

def now(): return datetime.now(timezone.utc).isoformat()

def queue_poll_delay(poll, *, idle=False, failures=0):
    """Keep active handoffs responsive; don't hammer an idle or unavailable DB."""
    if failures:
        return min(300, max(30, poll) * 2 ** min(failures - 1, 4))
    return max(60, poll) if idle else poll
def write_state(state):
    HOME.mkdir(parents=True,exist_ok=True)
    target=HOME/'status.json'; temp=HOME/'status.tmp'
    temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    # Windows readers/antivirus may briefly hold the destination open.
    for attempt in range(8):
        try:
            temp.replace(target)
            return True
        except PermissionError:
            time.sleep(.05 * (attempt + 1))
    import logging
    logging.warning('Local media status file is busy; retrying on the next update')
    return False

@contextlib.contextmanager
def singleton():
    HOME.mkdir(parents=True,exist_ok=True)
    with (HOME/'manager.lock').open('a+b') as stream:
        stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt;msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl;fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError: raise RuntimeError('Local media manager is already running')
        yield

def pending_roles():
    import requests
    base=(os.getenv('NEXT_PUBLIC_SUPABASE_URL') or os.getenv('SUPABASE_URL') or '').rstrip('/')
    key=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
    if not base or not key: raise RuntimeError('Worker database connection is not configured')
    headers={'apikey':key,'Authorization':'Bearer '+key}
    def exists(table,params):
        response=requests.get(base+'/rest/v1/'+table,headers=headers,params={'select':'id','limit':'1',**params},timeout=(5,15))
        response.raise_for_status();return bool(response.json())
    from worker.workflow_roles import POSTPRODUCTION, asset_query
    from ae_scene_preparation import claimable_filter as simple_filter
    roles=[]
    for role,kind in [('filmcraft','filmcraft_automation'),('webtoon','horizontal_webtoon_automation'),('effectcraft','effectcraft_automation'),('motion_automation','motion_automation'),('motion_preview','motion_preview'),('region','region_motion_plan'),('ae','ae_mouth_job')]:
        from worker.production_engine_policy import alternatives_enabled
        if role in ('effectcraft','filmcraft') and not alternatives_enabled():continue
        query={'metadata->>kind':'eq.'+kind,'or':claimable_filter() if role=='ae' else simple_filter()}
        if role in ('motion_automation','filmcraft','webtoon','effectcraft'):query['and']='(or(metadata->>retry_after.is.null,metadata->>retry_after.lte.'+now()+'))'
        if role=='motion_preview':query['metadata->input->>task']='eq.preview'
        if role in ('filmcraft','webtoon','effectcraft','motion_automation','motion_preview'):query['metadata->>enabled']='eq.true'
        if role=='ae':query['metadata->>pipeline_version']='eq.2'
        if exists('std_project_assets',asset_query(POSTPRODUCTION,query)):roles.append(role)
    response=requests.get(base+'/rest/v1/remote_render_queue',headers=headers,params={
        'select':'metadata->std_web_project_id','limit':'1000','render_mode':'eq.gcs_api',
        'metadata->>std_web_project_id':'not.is.null','or':f"(status.eq.pending,and(status.eq.rendering,metadata->>pipeline_version.eq.2,updated_at.lt.{(datetime.now(timezone.utc)-__import__('datetime').timedelta(minutes=3)).isoformat()}))"},timeout=(5,15))
    response.raise_for_status()
    import re
    ids={row.get('std_web_project_id') for row in response.json() if re.fullmatch(r'[a-fA-F0-9-]{36}',str(row.get('std_web_project_id') or ''))}
    if ids and exists('std_projects',{'id':'in.('+','.join(ids)+')','submitted_at':'not.is.null','status':'not.in.(approved,canceled,cancelled,completed,paid)'}):roles.append('render')
    return roles

def role_command(role):
    from worker.production_engine_policy import require_engine
    require_engine(role)
    if role=='webtoon': return [sys.executable,'-u',str(ROOT/'worker/motion_automation_worker.py'),'--engine','webtoon','--once']
    if role=='filmcraft': return [sys.executable,'-u',str(ROOT/'worker/motion_automation_worker.py'),'--engine','filmcraft','--once']
    if role=='effectcraft': return [sys.executable,'-u',str(ROOT/'worker/motion_automation_worker.py'),'--engine','effectcraft','--once']
    if role=='motion_automation': return [sys.executable,'-u',str(ROOT/'worker/motion_automation_worker.py'),'--engine','ae','--once']
    if role=='motion_preview': return [sys.executable,'-u',str(ROOT/'worker/motion_preview_worker.py'),'--once']
    if role=='region': return [sys.executable,'-u',str(ROOT/'worker/ae_region_motion_worker.py'),'--once']
    if role=='ae': return [sys.executable,'-u',str(ROOT/'worker/ae_mouth_worker.py'),'--once','--mouth-only']
    if role=='render': return [sys.executable,'-u',str(ROOT/'remote_drive_worker.py'),'--once']
    raise ValueError('Unknown media role')

def busy_processes():
    if os.name!='nt':return []
    script = "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'aerender.exe' -or ($_.Name -eq 'effectcraft-cli.exe' -and $_.CommandLine -match '\\srender(\\s|$)') -or ($_.Name -match '^python(w)?\\.exe$' -and $_.CommandLine -match '(ae_scene_preparation|ae_region_motion_worker|ae_mouth_worker|ae_highlight_worker|remote_render_source|remote_drive_worker|motion_automation_worker|motion_preview_worker)\\.py') } | Select-Object ProcessId,Name | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell','-NoProfile','-Command',script],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
    if result.returncode:raise RuntimeError('Could not verify local media resources')
    rows=json.loads(result.stdout) if result.stdout.strip() else []
    return rows if isinstance(rows,list) else [rows]

def serve_status(port=3004):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from worker.local_media_dashboard import Snapshot
    from worker import local_production_settings as production
    snapshot = Snapshot()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.headers.get('Host')!=f'127.0.0.1:{port}':self.send_error(403);return
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://127.0.0.1:{port}':self.send_error(403);return
            if production.handle(self):return
            if self.path in ('/status','/health'):
                payload=(HOME/'status.json').read_bytes() if (HOME/'status.json').exists() else b'{}'
                content='application/json'
            elif self.path=='/':
                payload=(ROOT/'worker/local_media_status.html').read_text(encoding='utf-8').replace('__LOCAL_TOKEN__',production.TOKEN).encode('utf-8');content='text/html; charset=utf-8'
            elif self.path=='/jobs':
                payload=json.dumps(snapshot.read(),ensure_ascii=False).encode('utf-8');content='application/json; charset=utf-8'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',content);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(payload)
        def do_POST(self):
            if self.headers.get('Host')!=f'127.0.0.1:{port}':self.send_error(403);return
            if self.headers.get('Origin')!=f'http://127.0.0.1:{port}':self.send_error(403);return
            if not production.handle(self):self.send_error(404)
        do_PUT = do_POST
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start();return server

class Supervisor:
    def __init__(self,poll=10,queue=pending_roles,spawn=subprocess.Popen,include_highlight=False):
        self.poll=poll;self.queue=queue;self.spawn=spawn;self.include_highlight=include_highlight
        self.stop=threading.Event();self.failures={};self.retry_after={};self.last_role='render'
        self.state={'service':'air-local-media','pipeline_version':2,'pid':os.getpid(),'status':'starting','active':None,'roles':{},'started_at':now()}
    def choose(self,roles):
        if (HOME/'pause-render').exists():roles=[r for r in roles if r!='render']
        # Legacy topic/highlight discovery cannot bypass user submission.
        roles=[r for r in roles if r in ('filmcraft','ae','render','region','webtoon','effectcraft','motion_automation','motion_preview')]
        available=[r for r in roles if time.monotonic()>=self.retry_after.get(r,0)]
        if 'render' in available: return 'render'
        return next((r for r in available if r!=self.last_role),available[0] if available else None)
    def execute(self,role):
        LOGS.mkdir(parents=True,exist_ok=True)
        with (LOGS/(role+'.log')).open('a',encoding='utf-8') as log:
            log.write('\n'+now()+' started '+role+'\n');log.flush()
            kwargs={'cwd':str(ROOT),'stdin':subprocess.DEVNULL,'stdout':log,'stderr':log}
            if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
            child=self.spawn(role_command(role),**kwargs)
            self.state.update(status='working',active={'role':role,'pid':child.pid,'started_at':now(),'log':str(LOGS/(role+'.log'))})
            write_state(self.state)
            # Stop is graceful: finish the current job, then stop claiming new work.
            while child.poll() is None:
                self.state['updated_at']=now();write_state(self.state);self.stop.wait(1) if not self.stop.is_set() else time.sleep(1)
            code=child.returncode
        self.failures[role]=self.failures.get(role,0)+1 if code else 0
        self.retry_after[role]=time.monotonic()+min(300,30*self.failures[role]) if code else 0
        self.state['roles'][role]={'exit_code':code,'failures':self.failures[role],'status':'retry_wait' if code else 'idle','finished_at':now()}
        self.state.update(active=None,status='idle');self.last_role=role;write_state(self.state)
    def run(self,once=False):
        with singleton():
            write_state(self.state)
            queue_failures = 0
            try:
                while not self.stop.is_set() and not (HOME/'stop').exists():
                    try:
                        roles=self.queue();role=self.choose(roles)
                        queue_failures = 0
                        delay = queue_poll_delay(self.poll, idle=not roles)
                        self.state.update(status='idle',pending_roles=roles,updated_at=now(),render_paused=(HOME/'pause-render').exists())
                        self.state.pop('queue_error',None);write_state(self.state)
                        if role:
                            busy=busy_processes()
                            if busy:self.state.update(status='resources_busy',busy_processes=busy);write_state(self.state)
                            else:self.execute(role)
                    except Exception as error:
                        queue_failures += 1
                        delay = queue_poll_delay(self.poll, failures=queue_failures)
                        self.state.update(status='connection_error',queue_error=type(error).__name__,updated_at=now());write_state(self.state)
                    if once:break
                    self.stop.wait(delay)
            finally:self.state.update(status='stopped',active=None,updated_at=now());write_state(self.state)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--status',action='store_true')
    parser.add_argument('--stop',action='store_true');parser.add_argument('--pause-render',action='store_true');parser.add_argument('--resume-render',action='store_true')
    parser.add_argument('--include-highlight',action='store_true');parser.add_argument('--enable-highlight',action='store_true');parser.add_argument('--port',type=int,default=3004);parser.add_argument('--poll',type=float,default=10)
    args=parser.parse_args();HOME.mkdir(parents=True,exist_ok=True)
    if args.enable_highlight or args.include_highlight:parser.error('기존 하이라이트 자동 탐색은 종료되었습니다. 유저웹에서 제출한 작업만 실행합니다.')
    if args.status:print((HOME/'status.json').read_text(encoding='utf-8') if (HOME/'status.json').exists() else '{"status":"not_started"}');return
    if args.stop:(HOME/'stop').touch();return
    if args.pause_render:(HOME/'pause-render').touch();return
    if args.resume_render:(HOME/'pause-render').unlink(missing_ok=True);return
    with singleton(): pass  # Never clear another manager's stop request.
    (HOME/'stop').unlink(missing_ok=True)
    manager=Supervisor(max(1,args.poll),include_highlight=args.include_highlight)
    for name in ('SIGINT','SIGTERM'):
        if hasattr(signal,name):signal.signal(getattr(signal,name),lambda *_:manager.stop.set())
    server=None if args.once else serve_status(args.port)
    try:manager.run(args.once)
    finally:
        if server:server.shutdown()
if __name__=='__main__':main()
