"""Source-bound footage samples; never loop, stretch, pad or use the clip's audio."""
import math
from pathlib import Path
from ambient_loop import digest
CONTRACT = 'wuxia_state_clip/v1'

def prepare(timeline, directory, fresh, download, probe=None, decode=None):
    clips = [s for s in timeline['states'] if s.get('clip')]
    samples = timeline['samples']
    if not clips:
        if any(s.get('video') for s in samples):
            raise ValueError('Video samples have no attached state footage')
        return
    if timeline.get('state_clip_contract') != CONTRACT:
        raise ValueError('State footage requires an updated worker contract')
    if probe is None:
        from ae_scene_production import _video_info
        def probe(path):
            import imageio_ffmpeg
            info = _video_info(path)
            reader = imageio_ffmpeg.read_frames(str(path))
            try: info['codec'] = next(reader).get('codec', '')
            finally: reader.close()
            return info
    if decode is None:
        from ae_media_utils import run, ffmpeg
        decode = lambda path: run([ffmpeg(), '-v', 'error', '-i', str(path), '-map', '0:v:0', '-f', 'null', '-'])
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    known = {}
    for state in clips:
        clip = state['clip']
        if clip.get('contract') != CONTRACT or clip.get('source_state_sha256') != state['sha256']:
            raise ValueError('State footage source artwork changed')
        sha = clip.get('sha256', '')
        if not __import__('re').fullmatch('[a-f0-9]{64}', sha): raise ValueError('Invalid footage checksum')
        for key in ('duration_seconds', 'source_in_seconds', 'play_seconds', 'start_offset_seconds'):
            value = clip.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('Invalid footage timing')
        if not 0 < clip['play_seconds'] <= clip['duration_seconds'] <= 30 or clip['source_in_seconds'] + clip['play_seconds'] > clip['duration_seconds'] + 1e-6:
            raise ValueError('Footage interval exceeds source; looping/padding is forbidden')
        fresh(); suffix=Path(clip.get('gcs_path','clip.mp4')).suffix.lower()
        if suffix not in ('.mp4','.mov','.webm'): suffix='.mp4'
        path = directory / (sha + suffix)
        if not path.exists() or digest(path) != sha: download(clip, path)
        if digest(path) != sha: raise ValueError('State footage checksum mismatch')
        info = probe(path)
        if info.get('codec') != 'h264': raise ValueError('State footage must be H.264 MP4')
        if info['width'] != clip['width'] or info['height'] != clip['height'] or abs(info['duration'] - clip['duration_seconds']) > .15:
            raise ValueError('Actual footage canvas/duration differs from the attachment')
        if info['width'] < 640 or info['height'] < 360 or info['width'] * info['height'] > 16_000_000 or abs(info['width'] / info['height'] - 16 / 9) >= .01:
            raise ValueError('Invalid state footage canvas')
        if clip['source_in_seconds'] + clip['play_seconds'] > info['duration'] + 1e-6:
            raise ValueError('Actual footage is shorter than its selected interval')
        decode(path); fresh()
        clip['file'] = str(path.resolve())
        if clip['asset_id'] in known: raise ValueError('Duplicate state footage identity')
        known[clip['asset_id']] = (state['asset_id'], clip)
    previous = None
    for sample in samples:
        video = sample.get('video')
        if not video:
            previous = None; continue
        state_id, clip = known.get(video.get('asset_id'), (None, None))
        time = video.get('source_seconds')
        if state_id != sample['state'] or type(time) not in (int, float) or not math.isfinite(time):
            raise ValueError('Footage sample is not bound to its visible state')
        if not clip['source_in_seconds'] - 1e-7 <= time < clip['source_in_seconds'] + clip['play_seconds'] - 1e-7:
            raise ValueError('Footage sample exceeds selected interval')
        if previous and previous[0] == video['asset_id'] and abs((time - previous[1]) - (sample['at'] - previous[2])) > 1e-6:
            raise ValueError('Footage must play at normal speed')
        previous = (video['asset_id'], time, sample['at'])
        if sample.get('mouths') or sample.get('ambient') or sample.get('effects', {}).get('active') or sample.get('motion', {}).get('active'):
            raise ValueError('Still-art animation must not overlap footage')

def jsx(timeline):
    import json
    clips = []
    for state in timeline['states']:
        clip = state.get('clip')
        if not clip: continue
        keys = []; times = []; prior = False
        for sample in timeline['samples']:
            video = sample.get('video')
            active = bool(video and video['asset_id'] == clip['asset_id'])
            if active != prior: keys.append([sample['at'], 100 if active else 0]); prior = active
            if active: times.append([sample['at'], video['source_seconds']])
        clips.append({'file': clip['file'], 'keys': keys, 'times': times})
    return '''
    var WVC=''' + json.dumps(clips, ensure_ascii=True, allow_nan=False) + ''';
    for(var vi=0;vi<WVC.length;vi++){
      var vc=WVC[vi],vf=app.project.importFile(new ImportOptions(new File(vc.file))),vl=source.layers.add(vf);
      vl.name='wuxia_state_video_'+vi;vl.timeRemapEnabled=true;vl.inPoint=0;vl.outPoint=S.duration;vl.audioEnabled=false;
      var vt=vl.property('ADBE Transform Group'),fit=Math.max(W/vf.width,H/vf.height)*100;
      vt.property('ADBE Anchor Point').setValue([vf.width/2,vf.height/2]);vt.property('ADBE Position').setValue([W/2,H/2]);vt.property('ADBE Scale').setValue([fit,fit]);
      var vo=vl.property('Opacity');vo.setValueAtTime(0,0);
      for(var vk=0;vk<vc.keys.length;vk++)vo.setValueAtTime(vc.keys[vk][0],vc.keys[vk][1]);whold(vo);
      var tm=vl.property('ADBE Time Remapping');while(tm.numKeys)tm.removeKey(1);
      for(var vk=0;vk<vc.times.length;vk++)tm.setValueAtTime(vc.times[vk][0],vc.times[vk][1]);whold(tm);
    }
''' if clips else ''
