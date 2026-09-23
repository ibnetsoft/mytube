import json,sys,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parents[1]))
from moviepy import AudioFileClip,CompositeAudioClip
from imageio_ffmpeg import get_ffmpeg_exe
from services.comic_turn_audio import recorded_page_turns
source=root/'v7';out=root/'v8';out.mkdir(exist_ok=True)
manifest=json.loads((source/'manifest.json').read_text(encoding='utf8'))
paths=[root/'page-turn-audio'/f'page-turn-{i:02}.mp3' for i in range(1,5)]
voice=AudioFileClip(str(source/'speech.wav'))
tracks=[voice.subclipped(p['source_start'],min(p['source_end'],voice.duration)).with_start(p['start']) for p in manifest['pages']]
effects,resources=recorded_page_turns(paths,manifest['pages'],manifest['settings']['comic']['turn_duration'],.55)
audio=CompositeAudioClip(tracks+effects).with_duration(manifest['duration'])
audio.write_audiofile(str(out/'soundtrack.m4a'),fps=44100,codec='aac',bitrate='192k',logger=None)
audio.close();voice.close()
for r in resources:r.close()
subprocess.run([get_ffmpeg_exe(),'-y','-i',str(source/'output.mp4'),'-i',str(out/'soundtrack.m4a'),'-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart',str(out/'output.mp4')],check=True,capture_output=True)
for p in source.glob('page_*.png'):shutil.copyfile(p,out/p.name)
manifest['settings']['comic']['turn_sound_paths']=[str(p.resolve()) for p in paths]
manifest['settings']['comic']['turn_sound_volume']=.55
manifest['page_turn_sounds']=[{'transition':i+1,'sound':i%4+1,'start':p['end'],'duration':effects[i].duration} for i,p in enumerate(manifest['pages'][:-1])]
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
html=(source/'index.html').read_text(encoding='utf8').replace('3D 책장 넘김','3D 책장 넘김 · 실제 효과음 4종')
html=html.replace('<video id=', '<p>첨부한 책장 소리 1 → 2 → 3 → 4를 반복합니다. 총 12번의 전환에 각 소리가 3번씩 사용됩니다.</p><video id=')
(out/'index.html').write_text(html,encoding='utf8')
print('DONE: 12 transitions, sounds 1 2 3 4 repeated 3 times; video stream copied without re-encoding')
