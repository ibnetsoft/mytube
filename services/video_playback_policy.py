"""Native video playback only: never manufacture freeze, loop, or retimed tails."""
import math

POLICY = 'original_speed_no_freeze_no_loop/v1'

class VideoPlaybackError(ValueError):
    pass

def require_video_duration(source_duration, required_duration, fps=24, scene_number=None):
    values=(source_duration,required_duration,fps)
    if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in values):
        raise VideoPlaybackError('영상 길이 또는 FPS가 유효하지 않습니다.')
    # One frame of container timestamp rounding is not an authored held tail.
    if required_duration-source_duration > 1/fps+.001:
        label=f'{scene_number}번 씬: ' if scene_number is not None else ''
        raise VideoPlaybackError(f'{label}원본 영상 {source_duration:.3f}초 / 필요한 구간 {required_duration:.3f}초. 영상 길이가 부족합니다. 정지·반복·속도 변경 없이 사용할 영상을 준비해 주세요.')

def require_original_video_asset(asset, scene_number=None):
    meta=(asset or {}).get('metadata') or {}
    policy=str(meta.get('video_tail_policy') or meta.get('tail_policy') or '').lower()
    if meta.get('kind') in ('repaired_source_clip','motion_source_repair') or meta.get('source_repair') or any(x in policy for x in ('hold','freeze','loop')):
        raise VideoPlaybackError(f'{scene_number}번 씬: 정지·반복 처리가 기록된 수정본입니다. 원본 영상을 선택해 주세요.')
