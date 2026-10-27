"""Track mouths after the depth move, then composite patches without a second camera."""
import copy
from pathlib import Path

def apply(runner,job,snapshot,scene,visual,voice,directory,fresh):
    mouth=scene.get('parallax_mouth') or {}
    if not mouth.get('mouth_required'):return visual
    from submitted_video_postwork import prepare_mouth
    from ae_flat_scene import prepare
    from ae_scene_production import _render_native
    working=copy.deepcopy(scene)
    working.pop('still_mouth',None)
    working.update(source_kind='video',postwork=copy.deepcopy(mouth))
    receipt=prepare_mouth(runner,job,working,snapshot,Path(visual),voice,Path(directory)/'mouth',fresh)
    if not receipt:raise ValueError('Parallax dialogue mouth preparation missing')
    working['_mouth_runtime']=receipt['runtime']
    direction={'source':'video','fit':'contain','effects':[],
        'keys':[dict(t=t,x=.5,y=.5,scale=1,rotation=0,opacity=100) for t in (0,1)]}
    prepared=prepare(Path(visual),working,snapshot['motion'],direction)
    output_dir=Path(directory)/'mouth-composite';output_dir.mkdir(exist_ok=True)
    fresh();output=_render_native(prepared,output_dir,scene['end']-scene['start'])
    scene['_mouth_runtime']=receipt['runtime'];scene['_postwork_receipt']=receipt
    return output
