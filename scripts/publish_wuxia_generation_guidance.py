"""Publish explicitly authorized baseline guidance for all connected script workers.
Run with --apply after loading trusted worker credentials. Never publishes media.
"""
import argparse,json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def baseline_row():
    policy=json.loads((ROOT/'docs/wuxia-generation-rules.json').read_text())
    instruction=('모든 대본 워커 공통: 무협 웹툰 작업에 아래 기준을 생성 전에 확인하고 적용한다. 다른 장르에는 무협 고유 설정을 강제하지 않는다. '
        '대본·이미지 프롬프트·영상 지침·AE 지침은 사용자 승인 단계별로 진행한다. 실제 이미지 생성이나 검수를 했다고 꾸미지 않는다.\n'
        '각 항목에 대해 실제 참조 관찰, 이번 입력에 반영할 내용, 생성 후 새 그림의 확인 방법을 기록한다. '
        '기존 회차/대본/음성은 보존한다. 불합격·불확실 이미지는 다음 컷의 승인 참조나 미리보기/AE에 사용하지 않는다.\n'
        +'\n'.join(r['title']+': '+r['instruction'] for r in policy['rules']))
    assert len(instruction)<=4000
    identity=str(uuid.uuid5(uuid.NAMESPACE_URL,'air:wuxia-generation-guidance:'+instruction))
    return {'id':identity,'title':f"무협 생성 전 지침 확인·원화 검수 필수 기준 {policy['revision']}판",'issue':'반복된 손 좌우·단검 변형·석상 상태 불연속과 원인 설명 누락 방지. 사용자 2026-11-24 공통 적용 요청.', 'instruction':instruction,'category':'','language':''}

def publish(store):
    from worker.script_guidelines import review
    row=baseline_row()
    existing,_=store.request('GET','script_guideline_versions',params={'id':'eq.'+row['id'],'select':'id,version,status,instruction'})
    if existing:
        saved=existing[0]
        if saved['instruction']!=row['instruction']:raise ValueError('동일 ID 내용 불일치')
        if saved['status'] not in ('approved','pending'):raise ValueError('이미 비활성화된 지침은 자동 재승인하지 않습니다.')
    else:
        rows,_=store.request('POST','script_guideline_versions',body={**row,'status':'pending'},prefer='return=representation');saved=rows[0]
    if saved['status']=='pending':saved=review(store,row['id'],'approve','2026-11-24 사용자가 모든 대본생성 워커 공통 적용을 명시적으로 지시함.')
    rows,_=store.request('GET','script_guideline_versions',params={'id':'eq.'+row['id'],'select':'id,version,status,instruction'})
    assert len(rows)==1 and rows[0]['status']=='approved' and rows[0]['instruction']==row['instruction']
    return {k:rows[0][k] for k in ('id','version','status')}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--env-file',default='worker/connection.env');args=parser.parse_args()
    if not args.apply:
        print(json.dumps(baseline_row(),ensure_ascii=False,indent=2));return
    from dotenv import load_dotenv
    load_dotenv(args.env_file,override=False)
    from worker.script_worker_store import ScriptStore
    print(json.dumps(publish(ScriptStore()),ensure_ascii=False))
if __name__=='__main__':main()
