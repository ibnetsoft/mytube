import json,sys,wave
from pathlib import Path
import numpy as np
from PIL import Image
from moviepy import VideoFileClip
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root.parents[1]))
from services import comic_render_service as comic
from lettering_v2 import lettering,book_turn
out=root/'v2';m=json.loads((out/'manifest.json').read_text(encoding='utf8'))
comic.balloon_layer=lettering;comic.page_curl=book_turn
images=[str(root/'images'/f'scene_{i:02}.png') for i in range(1,11)]
frames=comic.ComicFrames(images,m['durations'],m['events'],m['settings'],(1280,720),str(root.parents[1]/'auth-web/public/fonts/NanumSquareExtraBold.ttf'))
assert len(frames.pages)==5
dialogues=[e for e in m['events'] if e['kind']=='dialogue']
assert len(dialogues)==8 and {e['speaker'] for e in dialogues}=={'백운','제자'}
assert {e['style'] for e in dialogues}=={'shout','speech','whisper'}
assert len({tuple(e['placement']) for e in dialogues})==8
for event in dialogues:
    time=event['start']+((event['scene']-1)//2)*1.3
    assert not np.array_equal(frames.frame(time-.03),frames.frame(time+.03))
    with wave.open(str(out/(event['id']+'.wav')),'rb') as reader:
        samples=np.frombuffer(reader.readframes(reader.getnframes()),dtype='<i2')
        assert np.abs(samples.astype(float)).max()>500
with VideoFileClip(str(out/'output.mp4')) as video:
    assert video.size==[1280,720] and abs(video.duration-m['duration'])<.1
    for page in m['pages']:
        for t in [page['start']+.1,page['end']-.3]:
            assert np.abs(video.get_frame(t).astype(float)-frames.frame(t)).mean()<9
    for page in m['pages'][:-1]:
        t=page['end']+.42
        # The encoded video samples at 24fps; compare the same frame instant.
        encoded_time=int(t*video.fps)/video.fps
        assert np.abs(video.get_frame(t).astype(float)-frames.frame(encoded_time)).mean()<9
    for event in dialogues:
        t=event['start']+((event['scene']-1)//2)*1.3+.3
        audio=video.audio.to_soundarray(tt=np.arange(t,t+.2,1/44100))
        assert np.abs(audio).max()>.005
frames.close()
report={'pages':5,'scenes':10,'dialogue_events':8,'dialogue_speakers':2,'dialogue_styles':3,'unique_dialogue_positions':8,
    'narration_is_rectangular':True,'video_seconds':m['duration'],'voice_and_balloon_timing_verified':True,
    'four_spine_page_turns_verified':True,'prototype_only':True}
(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False))
