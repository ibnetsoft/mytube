"""Validate a supervised prefix-and-hold repair without changing frozen original assets."""
from pathlib import Path
import hashlib,math

def validate_repair(recipe,scene,source,audio_id):
    if not isinstance(recipe,dict) or recipe.get('contract')!='recorded_source_prefix/v1':raise ValueError('Invalid source repair contract')
    if scene.get('source_kind')!='video' or scene['source'].get('metadata',{}).get('ae_mouth_fingerprint'):raise ValueError('Source repair cannot retime recorded mouth clips')
    if recipe.get('source_asset_id')!=scene['source']['id'] or recipe.get('audio_id')!=audio_id:raise ValueError('Source repair belongs to another submitted scene')
    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=recipe.get('source_sha256'):raise ValueError('Source repair original checksum changed')
    count=recipe.get('retained_source_frames')
    if type(count) is not int or count<2:raise ValueError('Source repair must retain an original video prefix')
    duration=recipe.get('duration');fps=recipe.get('fps')
    if type(duration) not in (int,float) or type(fps) not in (int,float) or not math.isfinite(duration) or not math.isfinite(fps) or fps<=0:raise ValueError('Invalid source repair clock')
    if abs(duration-(scene['end']-scene['start']))>1/fps+.001:raise ValueError('Source repair changes finalized scene timing')
    return recipe

def verify_repair(recipe,source,repaired):
    import numpy as np
    from moviepy import VideoFileClip
    if hashlib.sha256(Path(repaired).read_bytes()).hexdigest()!=recipe.get('sha256'):raise ValueError('Source repair file checksum changed')
    maximum=0.;compared=0
    with VideoFileClip(str(source),audio=False) as original,VideoFileClip(str(repaired),audio=False) as output:
        fps=recipe['fps'];count=recipe['retained_source_frames']
        if abs(original.fps-fps)>.001 or abs(output.fps-fps)>.001 or count>original.duration*fps:raise ValueError('Source repair changes original playback rate')
        if original.size!=output.size or abs(output.duration-recipe['duration'])>.02:raise ValueError('Source repair canvas or duration changed')
        last=original.get_frame((count-1)/fps).astype('float32')
        for index,frame in enumerate(output.iter_frames(dtype='uint8')):
            expected=original.get_frame(index/fps).astype('float32') if index<count else last
            error=float(np.abs(expected-frame.astype('float32')).mean());maximum=max(maximum,error);compared+=1
        if not compared or maximum>3:raise ValueError('Source repair differs from the original prefix and held frame')
    return {'passed':True,'compared_frames':compared,'max_mean_absolute_error':maximum,'method':'original_speed_prefix_and_actual_frame_hold'}
