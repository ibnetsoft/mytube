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
# Continue only a version independently preferred on BOTH dimensions, with
# zero regressions at its selection. Preserve subsequent minor failed findings.
import listener_review
cache=OUTPUT_DIR/'codex_stage_requests'
accepted=[]
for report_path in cache.glob('local-'+JOB+'.02h_listener_compare.*response.json'):
 report=json.loads(report_path.read_text())
 if report.get('naturalness')==report.get('engagement') and report.get('naturalness') in ('A','B') and report.get('regressions')==[]:
  inp=json.loads(report_path.with_name(report_path.name.replace('.attempt-1.response.json','.input.json')).read_text())
  selected=inp['versions'][report['naturalness']]
  if selected!=repaired['sections']:accepted.append((report_path.stat().st_mtime,report_path,report,selected))
assert accepted,'No independently accepted improved manuscript; do not choose a rejected version'
_,selected_path,comparison,selected=max(accepted,key=lambda row:row[0])
validate_sections({'sections':selected},json.loads(next(cache.glob('local-'+JOB+'.02g_listener_repair.*input.json')).read_text())['scene_budgets'])
def continue_with_quality_notes(stage,title,sections,budgets,**kwargs):
 assert sections==repaired['sections'],'Source changed; supervised choice must be reviewed again'
 after={}
 for dimension in ('naturalness','engagement'):
  for report_path in cache.glob('local-'+JOB+'.02f_listener_'+dimension+'.*response.json'):
   inp_path=report_path.with_name(report_path.name.replace('.attempt-1.response.json','.input.json'))
   if json.loads(inp_path.read_text()).get('sections')==selected:
    report=json.loads(report_path.read_text());listener_review.validate_report(report,selected);after[dimension]=report
 assert len(after)==2,'Selected manuscript must have actual independent after-reviews'
 audit={'profile':listener_review.PROFILE,'mode':'text_only','verdict':'revise','selected':'revision','revision_rounds':1,
  'comparison':comparison,'after':after,'script_sha256':listener_review.digest(selected),
  'supervised_continuation':{'policy':'Record remaining quality findings separately and continue production with existing reviewed source',
   'actual_listener_verdict':'revise','not_a_listener_pass':True,'selection_report':str(selected_path)}}
 (OUT/'listener-quality-notes-continuation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
 print('CONTINUING_ACCEPTED_IMPROVEMENT_WITH_UNRESOLVED_LISTENER_QUALITY_NOTES',flush=True)
 return copy.deepcopy(selected),audit
listener_review.improve_for_listener=continue_with_quality_notes
import codex_content_runner
codex_content_runner.improve_for_listener=continue_with_quality_notes
request=console.StartRequest(**json.loads((OUT/'generation-request.json').read_text()))
row=console.jobs.start(request,None,retry_of=JOB,identity=JOB)
print('RESUMED_SAME_JOB',row['id'],flush=True)
console.jobs.pool.shutdown(wait=True)
print('RESUME_RESULT',console.jobs.rows[JOB]['status'],console.jobs.rows[JOB].get('stage'),flush=True)
