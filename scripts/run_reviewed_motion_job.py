"""Continue one authorized frozen AE job through technical retries and completion.

Never claims another job, bypasses review, changes source, or publishes/uploads.
The normal worker owns leases, backoff, source checks and atomic completion.
"""
import argparse,json,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
import worker_config
from worker.script_worker_store import ScriptStore

def main():
    p=argparse.ArgumentParser();p.add_argument('job_id',type=uuid.UUID);a=p.parse_args();job=str(a.job_id)
    store=ScriptStore();directory=ROOT/'output'/'reviewed-motion-continuation'/job;directory.mkdir(parents=True,exist_ok=True)
    while True:
        try:
            rows,_=store.request('GET','std_project_assets',params={'id':'eq.'+job,'select':'id,project_id,state:metadata->state,phase:metadata->phase,retry_after:metadata->retry_after,error:metadata->error'})
            if len(rows)!=1:raise ValueError('Target motion job not found')
            row=rows[0];project=store.request('GET','std_projects',params={'id':'eq.'+row['project_id'],'select':'status'})[0]
            (directory/'status.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
            if row['state']=='complete':print('AUTHORIZED_MOTION_JOB_COMPLETE',job,flush=True);return
            if row['state'] in ('canceled','cancelled') or not project or project[0]['status'] in ('approved','canceled','cancelled'):
                print('AUTHORIZED_MOTION_JOB_CLOSED',job,flush=True);return
            if row['state'] not in ('queued','processing'):raise ValueError('Unexpected job state; inspect without overriding it')
            # Claim/backoff eligibility and the common single-instance mutex are
            # enforced again inside the existing worker. No process is stopped.
            with (directory/'worker.log').open('ab') as log:
                result=subprocess.run([sys.executable,'-u',str(ROOT/'worker'/'motion_automation_worker.py'),'--engine','ae','--once','--job-id',job],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            print('AUTHORIZED_MOTION_JOB_RECHECK',job,'worker_exit',result.returncode,flush=True)
        except KeyboardInterrupt:raise
        except ValueError:raise
        except Exception as error:
            print('AUTHORIZED_MOTION_JOB_CONNECTION_RETRY',type(error).__name__,flush=True)
        time.sleep(30)
if __name__=='__main__':main()
