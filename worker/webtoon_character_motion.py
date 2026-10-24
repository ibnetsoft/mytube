"""Animate real separated PSD pixels; never fabricate a cutout or hidden plate."""
import math
from pathlib import Path

VIDEO_SUFFIXES={'.mp4','.mov','.webm','.mkv','.avi','.m4v'}

def validate_motion(plan):
    moves=plan.get('layer_motion',[])
    if not isinstance(moves,list) or len(moves)>32:raise ValueError('Invalid character layer motion')
    seen=set()
    def number(v,limit):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and abs(v)<=limit
    for move in moves:
        if not isinstance(move,dict):raise ValueError('Invalid character motion')
        layer=move.get('layer');anchor=move.get('anchor')
        if not isinstance(layer,int) or isinstance(layer,bool) or layer<1 or layer in seen:raise ValueError('Character layer must be unique and above the background')
        seen.add(layer)
        if not isinstance(anchor,list) or len(anchor)!=2 or not all(number(v,1) and v>=0 for v in anchor):raise ValueError('Invalid character pivot')
        for key in ('from','to'):
            pose=move.get(key,{})
            if not isinstance(pose,dict) or not isinstance(pose.get('offset'),list) or len(pose['offset'])!=2 or not all(number(v,.03) for v in pose['offset']) or not number(pose.get('rotation'),4):raise ValueError('Character motion exceeds restrained bounds')
    return moves

def psd_layers(source,directory):
    """Only independent normal top-level layers can be moved without blend changes."""
    from psd_tools import PSDImage
    from PIL import Image,ImageChops,ImageStat
    psd=PSDImage.open(source)
    layers=[]
    for layer in psd:
        if not layer.is_visible():continue
        if layer.clipping or layer.opacity!=255 or str(layer.blend_mode) not in ('BlendMode.NORMAL','BlendMode.PASS_THROUGH'):
            raise ValueError('인물 움직임은 불투명도 100%의 독립된 일반 PSD 레이어가 필요합니다.')
        rgba=layer.composite(viewport=(0,0,*psd.size),force=True)
        if rgba is None:raise ValueError('PSD 레이어를 읽을 수 없습니다.')
        rgba=rgba.convert('RGBA')
        if not rgba.getchannel('A').getbbox():continue
        target=directory/f'character-source-{len(layers)}.png';rgba.save(target)
        layers.append({'index':len(layers),'name':str(layer.name),'path':str(target.resolve()),'opaque':rgba.getchannel('A').getextrema()==(255,255)})
    if len(layers)<2 or not layers[0]['opaque']:raise ValueError('인물과 분리된 전체 배경 레이어가 필요합니다. 합쳐진 원화를 인물 동작으로 처리하지 않습니다.')
    if len(layers)>64:raise ValueError('PSD 레이어를 64개 이하의 인물·부위 그룹으로 정리해 주세요.')
    composite=Image.new('RGBA',psd.size)
    for item in layers:
        with Image.open(item['path']) as image:composite=Image.alpha_composite(composite,image.convert('RGBA'))
    expected=psd.composite(force=True).convert('RGB')
    if max(ImageStat.Stat(ImageChops.difference(composite.convert('RGB'),expected)).mean)>1:
        raise ValueError('PSD 분리 레이어의 원래 합성이 일치하지 않습니다. 혼합·마스크 그룹을 정리해 주세요.')
    return layers

def video_reference(source,directory,required,scene_number):
    from moviepy import VideoFileClip
    from PIL import Image
    with VideoFileClip(str(source),audio=False) as video:
        available=float(video.duration)
        if available+1e-6<required:
            raise ValueError(f'{scene_number}번 씬: 원본 영상 {available:.3f}초 / 필요한 구간 {required:.3f}초. 영상 길이가 부족합니다. 정지·반복·속도 변경 없이 사용할 영상을 준비해 주세요.')
        paths=[]
        for index,t in enumerate((0,required/2,max(0,required-1/max(1,video.fps)))):
            path=directory/f'video-source-{index}.png';Image.fromarray(video.get_frame(t)).save(path);paths.append(str(path.resolve()))
        return paths,available
