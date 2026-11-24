import copy,hashlib,json
from PIL import Image
import pytest
from worker import wuxia_generation_gate as g

def source(tmp_path,monkeypatch):
 monkeypatch.setattr(g,'ROOT',tmp_path);monkeypatch.setattr(g,'STATE',tmp_path/'updates')
 p=tmp_path/'source.png';Image.new('RGB',(10,10),'white').save(p)
 return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def plan(scene,ref):
 return {'scene_id':scene['scene_id'],'source_hash':g.digest(scene),'policy_sha256':g.policy()['sha256'],
 'rule_applications':{r['id']:{'observation':'실제 참조와 장면 상태 확인','input_action':'해당 조건을 생성 입력에 명시','verify_after_generation':'새 픽셀에서 형상과 상태 대조'} for r in g.policy()['rules']},
 'previous_art':{**ref,'observed_detail':'소매 아래 실제 틈 확인','regions':[[.1,.1,.4,.4]]},
 'prior_state':'석상 공격 중','current_state':'돌검 회수','result_state':'회전축 일시 정지','reuse_plan':'공간/단도 상태 재사용','pose_plan':'서진 오른팔-엄지 연속','camera_plan':'고정 접촉 근접',
 'contact_required':True,'contact':{k:'실제 구조 근거' for k in ('target_region','visible_structure','mechanism','consequence','setup_cut')},
 'assets':[{**ref,'asset_id':role,'state':'fixed_v1','role':role,'reviewed':True} for role in ('style','structure')],
 'required_asset_states':[],'actor_states':[{'id':'guardian01','position':'서쪽 홈 앞','facing':'서진','action_phase':'공격 회수'}]}

def test_missing_plan_never_returns_image_tool_arguments():
 scene={'scene_id':'S1'};r=g.preflight(scene,{})
 assert not r['ready'] and not r['reference_paths']
 with pytest.raises(ValueError,match='생성 입력 준비'):g.prepare_scene_imagegen_arguments(scene,'prompt',{})

def test_hash_state_contact_and_live_rule_changes_invalidate(tmp_path,monkeypatch):
 ref=source(tmp_path,monkeypatch);s={'scene_id':'S1'};p=plan(s,ref)
 assert g.preflight(s,p)['ready']
 args,receipt=g.prepare_scene_imagegen_arguments(s,'test',p);assert args['referenced_image_paths']==[ref['path']]
 bad=copy.deepcopy(p);bad['required_asset_states']=[{'asset_id':'dagger','state':'broken_v1'}]
 assert not g.preflight(s,bad)['ready']
 bad=copy.deepcopy(p);bad['contact'].pop('mechanism');assert not g.preflight(s,bad)['ready']
 g.update_rule(g.policy()['sha256'],'specific_recurrence','새 검사','새 구체 검사','사용자의 실제 문제 지적')
 assert not g.preflight(s,p)['ready']
 assert receipt['policy_sha256']!=g.policy()['sha256']
 with pytest.raises(ValueError):g.update_rule(receipt['policy_sha256'],'another_rule','제목','규칙','근거')

def test_text_or_old_approval_cannot_approve_changed_pixels(tmp_path,monkeypatch):
 ref=source(tmp_path,monkeypatch);p=g.policy()
 review={'source_sha256':ref['sha256'],'policy_sha256':p['sha256'],'checks':{r['id']:{'verdict':'pass','evidence':'실제 팔 연결/상태 대조','regions':[[0,0,1,1]]} for r in p['rules']}}
 assert not g.review_issues(review,ref['sha256'])
 review['checks']['anatomical_side']['verdict']='uncertain';assert g.review_issues(review,ref['sha256'])
 review['checks']['anatomical_side']['verdict']='not_applicable';assert g.review_issues(review,ref['sha256'])
 assert g.review_issues(review,'b'*64)
 Image.new('RGB',(10,10),'red').save(ref['path'])
 with pytest.raises(ValueError,match='변경'):g.verified_file(ref)

def test_latest_rules_are_loaded_into_generation_guidance(tmp_path,monkeypatch):
 from worker.script_worker_guidance import load_production_guidance
 monkeypatch.setattr(g,'STATE',tmp_path)
 before=load_production_guidance();assert g.policy()['sha256'] in before
 g.update_rule(g.policy()['sha256'],'never_reset','적 상태','공격 중인 적을 초기화하지 않는다','재발 사례')
 after=load_production_guidance();assert 'never_reset' in after and before!=after

def test_excluded_source_cannot_reenter_generation_or_render(tmp_path,monkeypatch):
 ref=source(tmp_path,monkeypatch);s={'scene_id':'S1'};p=plan(s,ref)
 g.exclude_source(ref['sha256'],'오른팔에 왼손')
 with pytest.raises(ValueError,match='사용 제외'):g.assert_sources_usable([ref])
 assert not g.preflight(s,p)['ready']

def test_native_ae_prepare_rejects_known_excluded_sha(tmp_path,monkeypatch):
 import sys
 sys.path.insert(0,str(g.SEED.parents[1]/'worker'))
 from worker.wuxia_native_timeline import prepare
 ref=source(tmp_path,monkeypatch);g.exclude_source(ref['sha256'],'사용자 해부학 반려')
 timeline={'contract':'wuxia_native_timeline/v6','states':[{'asset_id':'S1','sha256':ref['sha256']}],'samples':[]}
 with pytest.raises(ValueError,match='사용 제외'):prepare(timeline,tmp_path/'render',lambda:None,lambda *a:None,1,1)


def test_each_rule_requires_concrete_pre_generation_application(tmp_path,monkeypatch):
 ref=source(tmp_path,monkeypatch);scene={'scene_id':'S1'};p=plan(scene,ref)
 p.pop('rule_applications')
 assert not g.preflight(scene,p)['ready']
 p=plan(scene,ref);p['rule_applications']['weapon_axis_geometry']['input_action']=''
 assert not g.preflight(scene,p)['ready']
 p=plan(scene,ref);args,_=g.prepare_scene_imagegen_arguments(scene,'test',p)
 assert 'weapon_axis_geometry' in args['prompt'] and 'rule_applications' in args['prompt']


def test_failed_previous_art_cannot_seed_next_cut(tmp_path,monkeypatch):
 ref=source(tmp_path,monkeypatch);scene={'scene_id':'S1'};p=plan(scene,ref)
 g.exclude_source(ref['sha256'],'휘어진 칼과 뒤바뀐 손')
 p['repair_required']=True
 for item in p['assets']:item['role']='repair_target'
 assert any('직전' in item for item in g.preflight(scene,p)['issues'])


def test_worker_bundle_contains_persistent_rules():
 from scripts.build_script_worker_bundle import files,ROOT
 paths={p.relative_to(ROOT).as_posix() for p in files()}
 assert {'docs/wuxia-generation-rules.json','docs/WUXIA_GENERATION_GATE.md','worker/wuxia_generation_gate.py'} <= paths
