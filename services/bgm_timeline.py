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


def retime_bgm_settings(settings, subtitles, duration):
    """Recompute scene-bound BGM only after the final narration is known."""
    from services.scene_audio_anchor import resolve_scene_audio_anchor
    result = dict(settings)
    first, last = int(settings.get('bgm_start_scene') or 0), int(settings.get('bgm_end_scene') or 0)
    if first:
        if settings.get('bgm_start_anchor'):
            anchor = resolve_scene_audio_anchor(settings['bgm_start_anchor'], subtitles)
            if not anchor:
                raise ValueError('BGM start anchor changed or was deleted; review its scene selection')
            result['bgm_start'] = anchor['start']
        else:
            rows = [s for s in subtitles if str(s.get('scene_number')) == str(first)]
            number = int(settings.get('bgm_start_subtitle', 1))
            if number < 1 or number > len(rows):
                raise ValueError('BGM start subtitle is missing from the selected scene')
            result['bgm_start'] = float(rows[number - 1].get('start', 0))
    if last:
        ends = [float(s['end']) for s in subtitles if str(s.get('scene_number')) == str(last)]
        if not ends:
            raise ValueError('BGM end scene is missing from the final narration')
        result['bgm_end'] = max(ends)
    if (first or last) and not 0 <= float(result.get('bgm_start', 0)) < float(result.get('bgm_end', duration)) <= duration + .1:
        raise ValueError('BGM scene range is invalid on the final narration timeline')
    return result
