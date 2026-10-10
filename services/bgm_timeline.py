"""BGM window shared by the active FFmpeg renderer and its fallback."""
def bgm_window(settings, duration):
    start = max(0.0, min(duration, float(settings.get('bgm_start', 0) or 0)))
    end = max(start, min(duration, float(settings.get('bgm_end', duration) or duration)))
    length = end - start
    fade_in = min(length / 2, max(0.0, float(settings.get('bgm_fade_in', 2))))
    fade_out = min(length / 2, max(0.0, float(settings.get('bgm_fade_out', 2))))
    return start, end, fade_in, fade_out

def bgm_filter(settings, duration):
    start, end, fade_in, fade_out = bgm_window(settings, duration)
    length = end - start
    volume = max(0.0, min(1.0, float(settings.get('bgm_volume', .08))))
    filters = [f'atrim=duration={length:.6f}', 'asetpts=PTS-STARTPTS', f'volume={volume:.6f}']
    if fade_in: filters.append(f'afade=t=in:st=0:d={fade_in:.6f}')
    if fade_out: filters.append(f'afade=t=out:st={length-fade_out:.6f}:d={fade_out:.6f}')
    filters.append(f'adelay={round(start*1000)}:all=1')
    return ','.join(filters)
