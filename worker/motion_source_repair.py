"""Validate a supervised prefix-and-hold repair without changing frozen original assets."""
from pathlib import Path
import hashlib,math

def supervised_hold_limit(meta, scene, audio_id):
    """Only an explicit, audio/scene-bound supervised repair may exceed 5s."""
    approval=meta.get('supervised_source_repair') or {}
    if not approval or scene['number'] not in approval.get('scene_numbers',[]):return 5.0
    if (approval.get('contract')!='bounded_last_frame_hold/v1'
        or approval.get('source_audio_id')!=audio_id
        or not str(approval.get('authorization') or '').startswith('user_requested_')
        or meta.get('review_policy')!='complete_with_notes/v1'):
        raise ValueError('Invalid supervised source repair authorization')
    limit=approval.get('max_hold_seconds')
    if isinstance(limit,bool) or not isinstance(limit,(int,float)) or not math.isfinite(limit) or not 5<=limit<=7:
        raise ValueError('Supervised source hold must remain within 5..7 seconds')
    return float(limit)

def repair_short_video(scene, source, audio_id, directory, ffmpeg, run, max_hold=5.0):
    """Create and verify a bounded local execution copy, retaining the original asset."""
    from moviepy import VideoFileClip
    source=Path(source)
    with VideoFileClip(str(source),audio=False) as clip:
        available=float(clip.duration); fps=float(clip.fps)
    required=float(scene['end'])-float(scene['start'])
    gap=required-available
    if gap <= .001: return source, None
    if gap > max_hold: raise ValueError(f"{scene['number']}번 씬: 영상이 {gap:.2f}초 부족해 자동 보완 한도({max_hold:.1f}초)를 초과했습니다.")
    frames=round(available*fps)
    target_frames=math.ceil(required*fps-1e-6)
    duration=target_frames/fps
    target=Path(directory)/f"short-video-{scene['number']}.mp4"
    run([ffmpeg,'-v','error','-y','-i',str(source),'-an','-vf',f'tpad=stop_mode=clone:stop_duration={max(0,duration-available)+2/fps:.9f}', '-frames:v',str(target_frames),'-c:v','libx264','-crf','12','-preset','veryfast','-pix_fmt','yuv420p',str(target)])
    recipe={'contract':'recorded_source_prefix/v1','source_asset_id':scene['source']['id'],'audio_id':audio_id,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'retained_source_frames':frames,'duration':duration,'fps':fps,'hold_seconds':round(gap,6),'max_hold_seconds':max_hold}
    validate_repair(recipe,scene,source,audio_id)
    recipe['verification']=verify_repair(recipe,source,target)
    return target, recipe

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
        if abs(original.fps-fps)>.001 or abs(output.fps-fps)>.001 or (count-1)/fps>=original.duration:raise ValueError('Source repair changes original playback rate or exceeds the last source frame')
        if original.size!=output.size or abs(output.duration-recipe['duration'])>.02:raise ValueError('Source repair canvas or duration changed')
        last=original.get_frame((count-1)/fps).astype('float32')
        for index,frame in enumerate(output.iter_frames(dtype='uint8')):
            expected=original.get_frame(index/fps).astype('float32') if index<count else last
            error=float(np.abs(expected-frame.astype('float32')).mean());maximum=max(maximum,error);compared+=1
        if not compared or maximum>3:raise ValueError('Source repair differs from the original prefix and held frame')
    return {'passed':True,'compared_frames':compared,'max_mean_absolute_error':maximum,'method':'original_speed_prefix_and_actual_frame_hold'}
