"""Generate episode 2 packaging from finalized local narration using Codex CLI."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker.codex_content_runner import CodexStagedContentRunner
from worker.generation_validation import validated_stage
OUT=ROOT/'output/pawnshop-series/episode-02';JOB=json.loads((OUT/'job-receipt.json').read_text())['id']
BASE=ROOT/'output/codex-local-console'/JOB

def main():
 request=json.loads((OUT/'generation-request.json').read_text())
 candidate=json.loads((BASE/'candidate.json').read_text()) if (BASE/'candidate.json').exists() else {}
 if not candidate.get('script'):
  from worker_config import OUTPUT_DIR
  reviews=sorted((OUTPUT_DIR/'codex_stage_requests').glob('local-'+JOB+'.02i_post_listener_review.*response.json'),key=lambda p:p.stat().st_mtime)
  assert reviews,'Final continuity review required before packaging'
  review_path=reviews[-1];review=json.loads(review_path.read_text())['script_quality_report']
  assert review['verdict']=='pass' and not review['critical_issues'],'Final continuity review did not pass'
  source=json.loads(review_path.with_name(review_path.name.replace('.attempt-1.response.json','.input.json')).read_text())
  candidate={'script':source['script'],'structure':source['structure'],'main_character':source.get('main_character'),'supporting_characters':source.get('supporting_characters')}
  assert hashlib.sha256(json.dumps(source['sections'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()==json.loads((OUT/'listener-quality-notes-continuation.json').read_text())['script_sha256']
  (OUT/'packaging-source.json').write_text(json.dumps({'source_review':str(review_path),**candidate},ensure_ascii=False,indent=2))
 for folder in [OUT,ROOT/'docs/pawnshop-series/episode-02']:
  folder.mkdir(parents=True,exist_ok=True)
  (folder/'EPISODE_02_JA.md').write_text('# '+request['title']+'\n\n'+candidate['script']+'\n')
  lines=['# '+request['title']+' — Scenes','']
  for n,scene in enumerate(candidate['structure']['scenes'],1):lines.extend([f'## Scene {n}', '',str(scene.get('scene_text') or scene.get('narration') or ''),''])
  (folder/'EPISODE_02_SCENES_JA.md').write_text('\n'.join(lines))
 def validate(raw):
  titles=raw.get('title_candidates');assert isinstance(titles,list) and len(titles)==3
  assert all(isinstance(t,str) and 10<=len(t)<=100 for t in titles) and len(set(titles))==3
  assert raw.get('recommended_title') in titles
  assert isinstance(raw.get('description'),str) and 250<=len(raw['description'])<=4500
  assert isinstance(raw.get('tags'),list) and len(raw['tags'])>=5
  assert isinstance(raw.get('hashtags'),list) and len(raw['hashtags'])==3
  assert isinstance(raw.get('thumbnail_text'),str) and 3<=len(raw['thumbnail_text'])<=20
  assert isinstance(raw.get('thumbnail_prompt'),str) and len(raw['thumbnail_prompt'])>300
  assert isinstance(raw.get('story_fidelity_notes'),list) and raw['story_fidelity_notes']
  assert isinstance(raw.get('character_description'),dict) and all(isinstance(raw['character_description'].get(k),str) and raw['character_description'][k].strip() for k in ['wife','husband'])
 runner=CodexStagedContentRunner()
 existing_path=OUT/'youtube-packaging.json'
 existing=json.loads(existing_path.read_text()) if existing_path.exists() else None
 if existing and existing.get('script_sha256')!=hashlib.sha256(candidate['script'].encode()).hexdigest():existing=None
 raw=validated_stage(lambda n,c,t:existing if existing else runner._stage('pawnshop-'+JOB,n,c,t),'04p_youtube_packaging',
   {'story_title':request['title'],'script':candidate['script'],'scenes':candidate['structure']['scenes'],
    'character_anchors':candidate.get('character_anchors') or candidate['structure'].get('character_anchors'),
    'series':'Original adult contemporary Japanese supernatural pawnshop fantasy. photorealistic noir. Japanese audience.'},
   'Create honest JAPANESE YouTube packaging for the supplied FINAL original fictional narration. Read entire script and actual ending, do not invent scenes or claims. Preserve the original story title as a separate story_title. Return JSON {title_candidates:[3 distinct Japanese titles <=100 chars],recommended_title:one exact candidate,description:"Japanese description 250-4500 characters, brief compelling first lines, spoiler-light setup, clearly state original fiction; no full ending, no invented timestamps, no claims actual footage/finished render/real case or upload",tags:[5+ Japanese topical tags],hashtags:[exactly 3 Japanese hashtags],thumbnail_text:"one concise Japanese line 3-20 chars complementing title, not an invented direct quote",thumbnail_prompt:"English detailed 16:9 photorealistic thumbnail art direction grounded in final character design and story: a Japanese wife in her 40s, estranged husband distance, wedding ring motif and warm/cool contrast. One clear readable emotional focal point, natural non-celebrity faces, uncluttered composition, no fake proof or supernatural creatures not in script. Reserve negative space for separate Japanese copy; NO text/logos/watermarks in base art",story_fidelity_notes:[specific true source beats supporting packaging],spoiler_check:"explain kept ending undisclosed",character_description:{wife:"English exact face/hair/clothes grounded in final design",husband:"English exact face/hair/clothes grounded in final design"}}. Do not call image services or claim image exists.',validate)
 raw['script_sha256']=hashlib.sha256(candidate['script'].encode()).hexdigest()
 (OUT/'youtube-packaging.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2))
 metadata={**raw,'title':raw['recommended_title'],'story_title':request['title']}
 (OUT/'publish-metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
 text='# YouTube upload package\n\n## Recommended title\n\n'+raw['recommended_title']+'\n\n## Candidates\n\n'+'\n'.join(f'{i}. {t}' for i,t in enumerate(raw['title_candidates'],1))+'\n\n## Description\n\n'+raw['description']+'\n\n'+' '.join(raw['hashtags'])+'\n\n## Thumbnail text\n\n'+raw['thumbnail_text']+'\n\n## Tags\n\n'+', '.join(raw['tags'])+'\n'
 for dest in [OUT/'YOUTUBE_PACKAGE_JA.md',ROOT/'docs/pawnshop-series/episode-02/YOUTUBE_PACKAGE_JA.md']:dest.write_text(text)
 print(json.dumps({'recommended_title':raw['recommended_title'],'thumbnail_text':raw['thumbnail_text'],'script_sha256':raw['script_sha256']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
