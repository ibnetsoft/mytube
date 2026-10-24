import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from effectcraft_compatibility import linear_position_replacements


def project():
    keys=[dict(time=i,value=dict(v=v),in_interp='Linear',out_interp='Linear',
               spatial_auto=True,spatial_in=[0,0,0],spatial_out=[0,0,0])
          for i,v in enumerate([[0,0,0],[100,20,0],[0,40,0],[0,40,0]])]
    position=dict(match='position',spatial=True,keys=keys)
    return dict(items={'1':dict(id=1,kind=dict(type='Comp',layers=[dict(name='art',props=dict(children=[dict(match='transform',children=[position])]))]))})


def position(p):return p['items']['1']['kind']['layers'][0]['props']['children'][0]['children'][0]


def test_explicit_linear_contract_required_to_avoid_flattening_authored_auto_curves():
    p=project();original=copy.deepcopy(p)
    assert linear_position_replacements(p)==[]
    r,=linear_position_replacements(p,True)
    assert r['key_count']==4 and r['property']=='ADBE Position'
    assert p==original


def test_two_key_paths_and_already_explicit_paths_are_unchanged():
    p=project();position(p)['keys']=position(p)['keys'][:2]
    assert linear_position_replacements(p,True)==[]
    p=project()
    for k in position(p)['keys']:k['spatial_auto']=False
    assert linear_position_replacements(p,True)==[]


@pytest.mark.parametrize('case',['handle','temporal','roving','expression'])
def test_declared_linear_contract_rejects_ambiguous_authored_curves(case):
    p=project();prop=position(p);key=prop['keys'][1]
    if case=='handle':key['spatial_in']=[2,0,0]
    elif case=='temporal':key['out_interp']='Bezier'
    elif case=='roving':key['roving']=True
    else:prop['expression']='value+[time,0]'
    with pytest.raises(ValueError,match='review'):linear_position_replacements(p,True)
