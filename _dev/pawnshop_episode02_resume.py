"""Resume this failed job with the already repaired QA manuscript and a fresh independent review."""
import copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker import codex_local_console as console
from codex_content_runner import CodexStagedContentRunner
from worker.generation_validation import validate_sections
from worker_config import OUTPUT_DIR
OUT=ROOT/'output/pawnshop-series/episode-02';JOB=json.loads((OUT/'job-receipt.json').read_text())['id']
paths=sorted((OUTPUT_DIR/'codex_stage_requests').glob('local-'+JOB+'.02b_script_qa.*response.json'),key=lambda p:p.stat().st_mtime)
source=paths[-1];repaired=json.loads(source.read_text());used=False
original_stage=CodexStagedContentRunner._stage

def reuse_repaired_qa(self,job_id,name,context,task):
 global used
 if job_id=='local-'+JOB and name=='02b_script_qa' and not used:
  validate_sections(repaired,context['scene_budgets']);used=True
  (OUT/'recovery-reused-qa.json').write_text(json.dumps({'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'reason':'Reusing already corrected manuscript; independent final-narration review will execute again with corrected scope. Prior failed report is preserved; no score or verdict changed.'},ensure_ascii=False,indent=2))
  print('REUSED_REPAIRED_MANUSCRIPT; independent re-review required',flush=True)
  return copy.deepcopy(repaired)
 return original_stage(self,job_id,name,context,task)
CodexStagedContentRunner._stage=reuse_repaired_qa
request=console.StartRequest(**json.loads((OUT/'generation-request.json').read_text()))
row=console.jobs.start(request,None,retry_of=JOB,identity=JOB)
print('RESUMED_SAME_JOB',row['id'],flush=True)
console.jobs.pool.shutdown(wait=True)
print('RESUME_RESULT',console.jobs.rows[JOB]['status'],console.jobs.rows[JOB].get('stage'),flush=True)
