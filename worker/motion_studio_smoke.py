"""Isolated actual AE + Motion Studio export diagnostic; never touches project queues."""
import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'worker'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.exists() and any(directory.iterdir()):
        raise SystemExit('Use a new empty diagnostic directory; previous outputs are preserved.')
    directory.mkdir(parents=True, exist_ok=True)
    import worker_config
    import numpy as np
    from PIL import Image, ImageDraw
    from moviepy import VideoFileClip
    from ae_scene_effects_smoke import fixture
    from ae_scene_preparation import apply_motion_layer_edits
    from ae_scene_animation import validate_plan
    from ae_scene_production import _render_native
    from ae_media_utils import ffmpeg, run
    from services.motion_render_service import render_motion

    native_dir = directory / 'ae'
    prepared, _ = fixture(native_dir)
    keys = [dict(t=0, x=.5, y=.5, scale=1, rotation=0, opacity=100),
            dict(t=1, x=.51, y=.5, scale=1, rotation=1, opacity=100)]
    prepared['plan'] = validate_plan(apply_motion_layer_edits(prepared['plan'],
        {'layers': {'character': {'depth': .2, 'keys': keys}}}))
    (native_dir / 'authored-plan.json').write_text(json.dumps(prepared['plan'], indent=2), encoding='utf-8')
    native = _render_native(prepared, native_dir, 4)
    ae_video = native_dir / 'native-reviewed-sample.mp4'
    run([ffmpeg(), '-y', '-i', str(native), '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(ae_video)])
    audio = directory / 'calibration-tone.wav'
    with wave.open(str(audio), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes((np.sin(np.arange(8 * 16000) * 2 * np.pi * 440 / 16000) * 1000).astype('<i2').tobytes())
    scene = dict(source='image', fit='contain', direction='Independent diagnostic; preserve source artwork.',
        keys=[dict(t=0,x=.5,y=.5,scale=1,rotation=0,opacity=100),
              dict(t=1,x=.5,y=.5,scale=1.1,rotation=0,opacity=100)],
        effects=[dict(type='light_sweep',start=.1,end=.9,intensity=.5,center=[.5,.5],radius=.4,color=[1,.8,.4])],transition='cut')
    reports = []
    sheet = Image.new('RGB', (1280, 720), '#101820')
    for index, (aspect, size, fps) in enumerate([('16:9',(640,360),24),('9:16',(360,640),30)]):
        target = directory / ('landscape' if index == 0 else 'portrait')
        target.mkdir()
        settings = {'motion':dict(version=1,enabled=True,aspect=aspect,fps=fps,scenes={'1':scene,'2':{**scene,'source':'psd'}}),
                    'subtitle_font_family':'Arial','subtitle_text_color':'#ffffff','subtitle_bg_enabled':False}
        output = Path(render_motion(temp_dir=str(target), images=[str(native_dir/'source.png'),str(ae_video)],
            durations=[4,4], audio_path=str(audio), subtitles=[dict(start=0,end=4,text='Motion Studio - original image'),
            dict(start=4,end=8,text='Native AE - PSD layers')],settings=settings,resolution=size,scene_numbers=[1,2]))
        with VideoFileClip(str(output)) as video:
            assert video.size == list(size) and video.fps == fps and abs(video.duration - 8) < .08
            assert video.audio is not None and np.max(np.abs(video.audio.to_soundarray(fps=8000))) > .001
            assert not np.array_equal(video.get_frame(.2), video.get_frame(3.5))
            for column, seconds in enumerate([1,5]):
                frame = Image.fromarray(video.get_frame(seconds)); frame.thumbnail((640,330))
                sheet.paste(frame,(column*640,index*360+30))
                ImageDraw.Draw(sheet).text((column*640+8,index*360+8),f'{aspect} at {seconds}s',fill='white')
        reports.append(dict(aspect=aspect,fps=fps,duration=8,width=size[0],height=size[1],audio='calibration_tone_not_narration',
                            file=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
    sheet.save(directory/'contact-sheet.png')
    report = dict(state='rendered_requires_visual_review',native_ae=True,production_approved=False,outputs=reports)
    (directory/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
