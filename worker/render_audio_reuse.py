"""Replace the audio of a cached visual stream using the production mix recipe."""
from pathlib import Path
from services.bgm_timeline import bgm_filter
from worker.ae_media_utils import ffmpeg, run

def remux_audio_only(video, audio, directory, duration, settings, cues):
    from services.ffmpeg_slideshow_service import _resolve_audio_asset
    output = Path(directory) / 'output.mp4'
    command = [ffmpeg(), '-y', '-i', str(video), '-i', str(audio)]
    filters = [f'[1:a]atrim=duration={duration},asetpts=PTS-STARTPTS[voice]']
    labels, index = ['voice'], 2
    bgm = _resolve_audio_asset(directory, settings.get('bgm_path'))
    if bgm:
        if settings.get('bgm_loop', True): command += ['-stream_loop', '-1']
        command += ['-i', bgm]
        filters.append(f'[{index}:a]{bgm_filter(settings,duration)}[bgm]')
        labels.append('bgm');index += 1
    for number, cue in enumerate(cues):
        if cue.get('enabled') is False: continue
        source = _resolve_audio_asset(directory, cue.get('path') or cue.get('filename'))
        if not source: raise ValueError('Selected sound effect is missing')
        command += ['-i', source]
        trim = f"atrim=duration={float(cue['duration'])}," if cue.get('duration') else ''
        volume = float(cue['volume_db']) if cue.get('volume_db') is not None else -18
        start = cue.get('start') if cue.get('start') is not None else cue.get('time',0)
        label = f'sfx{number}'
        filters.append(f'[{index}:a]{trim}volume={volume}dB,adelay={int(float(start)*1000)}|{int(float(start)*1000)}[{label}]')
        labels.append(label);index += 1
    if len(labels)>1:
        filters.append(''.join(f'[{label}]' for label in labels)+f'amix=inputs={len(labels)}:duration=first:dropout_transition=0[mix]')
    command += ['-filter_complex',';'.join(filters),'-map','0:v:0','-map', '[mix]' if len(labels)>1 else '[voice]',
                '-c:v','copy','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(output)]
    run(command)
    return output
