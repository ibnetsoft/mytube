import copy,sys,json
from pathlib import Path
import pytest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'worker')]
from wuxia_effects import validate_samples
from wuxia_native_timeline import jsx

def timeline():
 f={'contract':'wuxia_effect_samples/v1','dx':8,'dy':-3,'scale':1.035,'overlays':[{'kind':'polygon','points':[[100,100],[104,102],[101,106]],'color':'#b7a38a','opacity':.2,'stroke':0}],'active':['debris_burst:0'],'issues':[]}
 return {'contract':'wuxia_native_timeline/v3','states':[{'asset_id':'a','file':'image.png','ambient_runtime':[],'mouth_runtime':[]}],'graphics':{},'samples':[{'at':0,'state':'a','graphics':[],'effects':f}]}

def test_frozen_vectors_and_rig_are_shared_by_art_and_patches_below_lettering():
 t=timeline();validate_samples(t);source,graphics=jsx(t,1,24);data=json.loads(source.split('var WT=',1)[1].split(';\n',1)[0]);assert data['effect_samples'][0]['dx']==8
 assert 'wuxia_art_impact_rig' in source and 'l.parent=wrig' in source and "wuxia_impact_vector_" in source
 assert 'wrig' not in graphics # lettering remains stable

@pytest.mark.parametrize('change',[{'dx':21},{'scale':1.1},{'issues':['unsafe_shake']},{'overlays':[{'kind':'javascript'}]}])
def test_invalid_frozen_frames_do_not_render(change):
 t=timeline();t['samples'][0]['effects'].update(change)
 with pytest.raises(ValueError):validate_samples(t)

def test_old_workers_cannot_silently_skip_new_effects_and_missing_samples_fail():
 t=timeline();t['contract']='wuxia_native_timeline/v2'
 with pytest.raises(ValueError,match='v3'):validate_samples(t)
 t=timeline();t['samples'][0].pop('effects')
 with pytest.raises(ValueError,match='Missing'):validate_samples(t)

def test_explicit_identity_frame_is_compact_but_executes_as_no_transform():
 t=timeline();t['samples'][0]['effects']={};validate_samples(t)
 source,_=jsx(t,1,24);data=json.loads(source.split('var WT=',1)[1].split(';\n',1)[0]);f=data['effect_samples'][0]
 assert (f['dx'],f['dy'],f['scale'],f['overlays'])==(0,0,1,[])

@pytest.mark.parametrize('duration',[1,3,5])
@pytest.mark.parametrize('axis',['dx','dy'])
def test_native_ae_keeps_every_fixed_rate_frame_without_smoothing(duration,axis):
 t=timeline();frames=[]
 for i in range(duration*24):
  f=copy.deepcopy(t['samples'][0]);f['at']=i/24
  f['effects'].update(dx=0,dy=0,overlays=[])
  f['effects'][axis]=(1 if (i*20//24)%2==0 else -1)*8
  frames.append(f)
 t['samples']=frames;validate_samples(t)
 source,_=jsx(t,duration,24)
 data=json.loads(source.split('var WT=',1)[1].split(';\n',1)[0])
 assert [(f['at'],f[axis]) for f in data['effect_samples']]==[(f['at'],f['effects'][axis]) for f in frames]
 assert 'whold(pos);whold(sca)' in source
 assert 'wiggle(' not in source # no AE-side frequency reinterpretation


def test_frozen_web_timeline_cannot_get_a_second_generic_camera_or_shake():
 from wuxia_native_timeline import bind_prepared
 prepared={'plan':{'effects':[{'type':'impact_shake'}],'lights':[{'type':'flash'}],'camera':[{'scale':1.2}],'fit':'contain','transition':{'out':'fade'}},'layers':{'original':'old.png'}}
 runtime={'size':[1672,941],'states':[{'file':'reviewed.png'}]}
 bound=bind_prepared(prepared,runtime)
 assert bound['plan']['wuxia_runtime'] is runtime
 assert bound['plan']['effects']==[] and bound['plan']['lights']==[]
 assert all(k['scale']==1 for k in bound['plan']['camera'])
 assert bound['plan']['transition']=={'in':'none','out':'none','fraction':0}
 assert bound['layers']['original']==Path('reviewed.png')


def test_state_pixel_sizes_are_preserved_and_cover_the_shared_output_canvas(tmp_path):
 from PIL import Image
 from ambient_loop import digest
 from wuxia_native_timeline import prepare
 states=[]
 for name,size in [('a',(32,18)),('b',(64,37))]:
  image=tmp_path/(name+'.png');Image.new('RGB',size,'red').save(image)
  states.append({'asset_id':name,'sha256':digest(image),'ambient_loops':[],'dialogue_mouths':[]})
 timeline={'contract':'wuxia_native_timeline/v1','states':states,'graphics':{},'samples':[{'at':0,'state':'a','graphics':[],'effects':{}},{'at':.5,'state':'b','graphics':[],'effects':{}}]}
 def download(ref,target):target.write_bytes((tmp_path/(ref['asset_id']+'.png')).read_bytes())
 runtime=prepare(timeline,tmp_path/'runtime',lambda:None,download,1,2)
 assert runtime['size']==[1920,1080]
 assert [s['canvas_size']for s in runtime['states']]==[[32,18],[64,37]]
 assert [digest(Path(s['file']))for s in runtime['states']]==[s['sha256']for s in states]
 source,_=jsx(runtime,1,2)
 assert 'Math.max(W/f.width,H/f.height)' in source
