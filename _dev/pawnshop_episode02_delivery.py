"""Write evidence-bounded episode 2 delivery notes and a private local bundle."""
import hashlib,json,shutil,sys,zipfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'worker')]
OUT=ROOT/'output/pawnshop-series/episode-02';DOC=ROOT/'docs/pawnshop-series/episode-02'
from dotenv import load_dotenv
load_dotenv(ROOT/'worker/connection.env')
from worker_config import OUTPUT_DIR

def main():
 receipt=json.loads((OUT/'registration-receipt.json').read_text());job=json.loads((OUT/'job-receipt.json').read_text())
 payload=json.loads((OUT/'topic-registration-payload.json').read_text());structure=payload['pregenerated_structure'];script=payload['pregenerated_script']
 assert hashlib.sha256(script.encode()).hexdigest()==receipt['script_sha256']
 packaging=json.loads((OUT/'youtube-packaging.json').read_text());assert packaging['script_sha256']==receipt['script_sha256']
 thumb=json.loads((OUT/'thumbnail-publication-receipt.json').read_text());assert thumb['script_sha256']==receipt['script_sha256']
 for role in ('background','final'):
  assert hashlib.sha256(Path(thumb[role]['local_path']).read_bytes()).hexdigest()==thumb[role]['sha256']
 audit=[]
 for prefix in ('local-'+receipt['job_id'],'pawnshop-'+receipt['job_id']):
  for p in sorted((OUTPUT_DIR/'codex_stage_requests').glob(prefix+'.*response.json'),key=lambda p:p.stat().st_mtime):
   try:d=json.loads(p.read_text())
   except ValueError:continue
   report=d.get('script_quality_report',d)
   if any(k in report for k in ('verdict','regressions','critical_issues')):
    audit.append({'stage':p.name.split('.')[1],'artifact':str(p),'artifact_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'report':report})
 assert audit,'Actual stage reports must be included'
 (OUT/'GENERATION_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
 listener=json.loads((OUT/'listener-quality-notes-continuation.json').read_text())
 notes=['# 2화 품질·완료 상태','',f"- 주제 #{receipt['topic_id']}: {receipt['title']}",f"- 일본어 본문 {len(script):,}자, {len(structure['scenes'])}씬. 목표 35분이며 실제 녹음 길이는 미측정.",f"- 본문 SHA256: {receipt['script_sha256']}",'- 대본·씬별 프롬프트·레이어 지시문·유튜브 제목 후보/추천·설명문·실제 썸네일 및 원본·유저웹 등록 완료.','- 전체 씬 이미지, 개별 레이어 PNG/PSD, TTS, 최종 AE 렌더는 미실행. 관리자 게시와 YouTube 업로드는 별도.','', '## 실제 검수와 수정 이력','', '- 최초 QA에서 다른 세계의 서류 반출과 날짜 표현 문제를 지적받아 수정했다. 이전 원고와 실패 검수 기록은 단계 캐시에 보존했다.','- 검수 입력에서 오래된 기획·연속성 장부를 제외한 것을 필수 누락으로 오판했다. 본문 전용 검수 범위를 명시하고 현재 원문으로 연속성을 재구성하도록 수정했다.','- 청취 수정 응답이 최소 글자 수에 미달한 오류를 수정 응답 검증·재요청으로 복구했다.','- 수정본 비교의 보완 의견도 다음 제한된 수정 요청에 전달하도록 보완했다.','- 복구 도구의 모듈 참조가 다른 경로를 가리켜 보정본이 한 차례 선택되지 않았다. 실제 워크플로 모듈에 맞춰 수정하고 보정본 재사용 기록을 남겼다.','- 로컬 콘솔 테스트 실행 중 로컬 상태 파일에 일시적 interrupted 표시가 생겼으나 실행 중인 작업의 DB 진행은 유지됐다. 이후 활성 제작 중 콘솔 테스트 실행을 피했다.','', '## 남아 있는 청취 품질 지적','', '- 실제 청취 판정: revise. 통과로 변경하지 않았다. 비교에서 양쪽 항목 모두 선호되고 퇴행 지적이 없었던 수정본을 선택한 뒤, 남은 품질 지적을 보존하고 생산을 계속했다.']
 story_review=json.loads((OUT/'independent-story-review.json').read_text())
 for note in story_review.get('quality_notes',[]):notes.append('- Final story review note: '+note)
 notes.append('- BGM/SFX plans are prompts only; no music or effects audio was rendered.')
 for dimension,report in listener['after'].items():
  for item in report.get('issues',[]):notes.append(f"- {dimension}, scene {item['scene_order']}: {item['reason']} / suggestion: {item['suggestion']}")
 notes+=['','## 최종 확인','', '- 선택 원고의 후속 연속성 검수와 별도 이야기 검수 결과는 실제 보고서를 보존했다. 청취 품질의 revise 판정과 구분한다.','- 1~18씬 단일 이미지, 19~50씬 별도 레이어 지시문, 51씬 이후 단일 이미지 범위 검증. 느린 줌 제거 및 짧은 카메라 이동 구간·정지 유지.','- 썸네일 실제 이미지 육안 확인, 일본어 문구 대조, GCS 재다운로드 해시 대조.','- 유저웹 등록 후 대본·전체 씬 구조·언어·상태·작업 ID·본문 해시 재조회.','- 로컬 스타일 프리셋 조회에서 SQLite 테이블 부재 경고와 기본 스타일 대체가 있었다. 명시한 현대 일본·일본어·실사 지시와 최종 결과 검수를 별도로 적용했다.','- 전체 단계 보고서: output/pawnshop-series/episode-02/GENERATION_AUDIT.json','']
 for p in (OUT/'QUALITY_NOTES.md',DOC/'QUALITY_NOTES.md'):p.write_text('\n'.join(notes))
 for name in ('EPISODE_02_JA.md','EPISODE_02_SCENES_JA.md','YOUTUBE_PACKAGE_JA.md'):
  shutil.copy2(OUT/name,DOC/name)
 bundle_names=['EPISODE_02_JA.md','EPISODE_02_SCENES_JA.md','YOUTUBE_PACKAGE_JA.md','QUALITY_NOTES.md','youtube-packaging.json','publish-metadata.json','topic-registration-payload.json','registration-receipt.json','thumbnail-art.png','thumbnail-final.png','thumbnail-youtube.jpg','thumbnail-source/prompts.json','thumbnail-review.json','thumbnail-publication-receipt.json','listener-quality-notes-continuation.json','GENERATION_AUDIT.json','user-web-verification.json']
 sums=[]
 for name in bundle_names:
  path=OUT/name;assert path.is_file(),name;sums.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+name)
 (OUT/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n')
 target=OUT/'EPISODE_02_DELIVERY.zip'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
  for name in bundle_names+['SHA256SUMS.txt']:z.write(OUT/name,name)
 with zipfile.ZipFile(target) as z:assert z.testzip() is None
 print(json.dumps({'topic_id':receipt['topic_id'],'scene_count':len(structure['scenes']),'script_chars':len(script),'zip_bytes':target.stat().st_size,'script_sha256':receipt['script_sha256'],'registered_elapsed_seconds':datetime.fromisoformat(receipt['registered_at']).timestamp()-job['created_at']},ensure_ascii=False))
if __name__=='__main__':main()
