import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from services.comic_render_service import ComicFrames, LAYOUTS, build_timeline, comic_enabled, page_curl, render_comic
from services.comic_lettering import caption_layers

FONT = str(Path('auth-web/public/fonts/NanumSquareExtraBold.ttf').resolve())

def test_following_page_visible_before_half_turn():
    old=np.full((180,320,3),[180,30,20],dtype=np.uint8)
    new=np.full_like(old,[20,40,220])
    frame=page_curl(old,new,.25)
    assert (frame[:,-10:,2]>150).any()
    assert not np.array_equal(frame[20],frame[160])  # slanted curved edge

def test_tail_root_has_no_internal_ellipse_stroke():
    layers=caption_layers((500,400),[{'text':'대사','start':0,'dialogue_kind':'dialogue',
        'comic':{'x':.2,'y':.25,'width':.4,'target_x':.9,'target_y':.35}}],FONT,24)
    canvas=Image.new('RGBA',(500,400));_,image,position=layers[0];canvas.paste(image,position,image)
    # Right-most body midpoint lies inside the continuous tail, not a black seam.
    assert min(canvas.getpixel((298,140))[:3])>180
    narration=caption_layers((500,400),[{'text':'설명','start':0,'comic':{'x':.2,'y':.25,'width':.4}}],FONT,24)
    assert narration[0][1].width<=204

def test_mixed_page_layouts_and_transparent_breakout(tmp_path):
    paths=fixtures(tmp_path)
    settings={'comic':{'version':1,'mode':'comic','layout':'single','page_layouts':{'0':'single','1':'spread'}}}
    frames=ComicFrames(paths,[1,1,1],[],settings,(640,360),FONT)
    assert [(p['first'],p['last'],p['layout']) for p in frames.pages]==[(0,1,'single'),(1,3,'spread')]
    frames.close()
    from PIL import ImageDraw
    cutout=Image.new('RGBA',(320,360));ImageDraw.Draw(cutout).ellipse((80,10,240,350),fill='red')
    cutout.save(tmp_path/'cutout.png')
    settings['comic'].update(layout='breakout',page_layouts={})
    frames=ComicFrames([paths[0],str(tmp_path/'cutout.png')],[1,1],[],settings,(640,360),FONT)
    frame=frames.page(0,1.9,True)
    assert frame[15,480,0]>180  # foreground above the base panel border
    frames.close()

@pytest.mark.parametrize('layout',[key for key in LAYOUTS if key!='breakout'])
def test_layouts_render_without_missing_scenes(tmp_path,layout):
    paths=fixtures(tmp_path)
    frames=ComicFrames(paths,[1,1,1],[],{'comic':{'version':1,'mode':'comic','layout':layout}},(640,360),FONT)
    assert sum(p['last']-p['first'] for p in frames.pages)==3
    assert frames.frame(.5).shape==(360,640,3)
    frames.close()


def test_opt_in_and_layout_contract():
    assert not comic_enabled({})
    assert not comic_enabled({'comic': {'mode': 'comic'}})
    assert not comic_enabled({'comic': {'version': 2, 'mode': 'comic'}})
    assert comic_enabled({'comic': {'version': 1, 'mode': 'moving_comic'}})
    assert LAYOUTS == json.loads(Path('auth-web/public/comic/layouts.json').read_text())


def test_page_timeline_preserves_all_narration_and_odd_last_page():
    starts, pages, total = build_timeline([1, 2, 3, 4, 5], 2, .7)
    assert starts == [0, 1, 3, 6, 10, 15]
    assert pages[1]['start'] == 3.7
    assert pages[2]['first'] == 4 and pages[2]['last'] == 5
    assert total == 16.4
    assert sum(p['source_end'] - p['source_start'] for p in pages) == 15
    with pytest.raises(ValueError):
        build_timeline([1, float('nan')], 2, .7)


def test_curl_exact_endpoints_and_visible_fold():
    a = np.full((90, 160, 3), [180, 40, 30], dtype=np.uint8)
    b = np.full_like(a, [20, 60, 170])
    assert np.array_equal(page_curl(a, b, 0), a)
    assert np.array_equal(page_curl(a, b, 1), b)
    half = page_curl(a, b, .5)
    assert np.array_equal(half[30, 10], a[30, 10])
    assert half[30, 85, 2] > half[30, 85, 0]  # next artwork, never a white reverse
    assert half[30, 150, 2] > 150  # revealed next page


def test_leaf_hinge_and_back_texture_orientation():
    from services.comic_page_turn import leaf_mesh
    for p in (.1,.4,.7,.95):
        vertices,_,_=leaf_mesh(p,320,180)
        assert np.all(vertices[:,0,0]==160)
        assert np.all(vertices[:,0,2]==0)
        assert vertices[:,-1,2].max()>0
    old=np.full((180,320,3),[180,20,20],dtype=np.uint8)
    new=np.zeros_like(old);new[:,:80]=[20,220,20];new[:,80:160]=[20,20,220];new[:,160:]=[220,180,20]
    frame=page_curl(old,new,.99)
    assert frame[90,35,1]>180  # outer edge of next LEFT page is correctly oriented
    assert frame[90,120,2]>180


def fixtures(tmp_path):
    paths = []
    for i, color in enumerate(['#284965', '#965640', '#487060']):
        p = tmp_path / f'{i}.png'
        Image.new('RGB', (320, 360), color).save(p)
        paths.append(str(p))
    return paths


def test_balloon_persists_after_its_dialogue_and_page_freezes(tmp_path):
    frames = ComicFrames(fixtures(tmp_path), [1, 1, 1], [
        {'start': .2, 'end': .5, 'text': '첫 번째 대사'},
        {'start': 1.2, 'end': 1.5, 'text': '두 번째 대사'},
    ], {'comic': {'version': 1, 'mode': 'comic', 'layout': 'spread'}}, (640, 360), FONT)
    try:
        first = frames.frame(.1)
        later = frames.frame(.7)
        both = frames.frame(1.7)
        assert not np.array_equal(first[:, :310], later[:, :310])
        assert np.array_equal(later[:, :310], both[:, :310])
        assert not np.array_equal(later[:, 325:], both[:, 325:])
        assert frames.frame(2.35).shape == (360, 640, 3)
    finally:
        frames.close()


def test_real_image_and_moving_comic_export(tmp_path):
    from moviepy import AudioClip, AudioFileClip, VideoClip, VideoFileClip
    paths = fixtures(tmp_path)
    audio_path = str(tmp_path / 'voice.wav')
    audio = AudioClip(lambda t: .12 * np.sin(2 * np.pi * 440 * np.asarray(t)), duration=3, fps=44100)
    audio.write_audiofile(audio_path, logger=None)
    audio.close()
    # A clip whose intensity changes lets us verify frozen and moving frames.
    clip_path = str(tmp_path / 'moving.mp4')
    clip = VideoClip(lambda t: np.full((180, 160, 3), [int(30 + t * 100), 90, 150], dtype=np.uint8), duration=1)
    clip.write_videofile(clip_path, fps=24, codec='libx264', logger=None)
    clip.close()
    for mode in ['comic', 'moving_comic']:
        folder = tmp_path / mode
        folder.mkdir()
        settings = {'comic': {'version': 1, 'mode': mode, 'layout': 'spread', 'turn_duration': .5, 'turn_sound': False}}
        frames = ComicFrames([clip_path, clip_path] + paths[2:], [1, 1, 1], [], settings, (640, 360), FONT)
        try:
            changed = not np.array_equal(frames.frame(.1)[:, :310], frames.frame(.7)[:, :310])
            assert changed == (mode == 'moving_comic')
            assert np.array_equal(frames.frame(.1)[:, 325:], frames.frame(.7)[:, 325:])
            assert (not np.array_equal(frames.frame(.1)[:, 325:], frames.frame(1.7)[:, 325:])) == (mode == 'moving_comic')
            assert np.array_equal(frames.frame(1.1)[:, :310], frames.frame(1.8)[:, :310])
        finally:
            frames.close()
        output = render_comic(temp_dir=str(folder), images=[clip_path] + paths[1:], durations=[1, 1, 1],
            audio_path=audio_path, subtitles=[{'start': .2, 'text': '안녕!'}, {'start': 1.2, 'text': '반가워!'}, {'start': 2.1, 'text': '다음 페이지'}],
            settings=settings, resolution=(640, 360))
        with VideoFileClip(output) as result:
            assert result.size == [640, 360]
            assert abs(result.duration - 3.5) < .08
            assert result.audio is not None
            silent = result.audio.to_soundarray(tt=np.array([2.15, 2.25, 2.35]))
            assert np.max(np.abs(silent)) < .02
            assert np.max(np.abs(result.audio.to_soundarray(tt=np.arange(2.6, 2.65, 1/44100)))) > .03
        assert len(list((folder / 'comic_pages').glob('*.png'))) == 2


def test_worker_dispatch_is_strictly_opt_in(monkeypatch):
    import ast
    import services.comic_render_service as service
    tree = ast.parse(Path('services/remote_render_service.py').read_text(encoding='utf-8-sig'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'remote_render_executor_func')
    worker_body = next(n for n in function.body if isinstance(n, ast.Try)).body
    index = next(i for i, n in enumerate(worker_body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'comic_options' for t in n.targets))
    body = worker_body[index:index + 2]
    body.append(ast.Return(ast.Constant('legacy')))
    wrapper = ast.FunctionDef(name='dispatch', args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]), body=body, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[wrapper], type_ignores=[]))
    called = []
    monkeypatch.setattr(service, 'render_comic', lambda **kw: called.append(kw))
    env = dict(temp_dir='tmp', images=['a'], durations=[1], audio_path='voice', subs=[{'text':'hi'}],
               metadata={'use_subtitles':True,'scene_numbers':[8]}, target_resolution=(1280,720), sfx_cues=[], update_progress=lambda *_: None)
    exec(compile(module, '<worker-dispatch>', 'exec'), env)
    for settings in [{}, {'comic': {'mode':'comic'}}, {'comic': {'version':1,'mode':'standard'}}]:
        env['render_settings'] = settings
        assert env['dispatch']() == 'legacy'
        assert called == []
    env['render_settings'] = {'comic': {'version':1,'mode':'comic'}}
    assert env['dispatch']() is None
    assert called[0]['scene_numbers'] == [8]
    assert called[0]['subtitles'] == [{'text':'hi'}]


def test_balloon_pop_is_bounded_and_settles():
    from services.comic_render_service import balloon_pop_scale, animated_balloon
    samples=[balloon_pop_scale(t) for t in np.linspace(0,.36,100)]
    assert min(samples)>=.72 and max(samples)<=1
    assert balloon_pop_scale(.198)>balloon_pop_scale(.2808)
    assert balloon_pop_scale(.36)==1 and balloon_pop_scale(10)==1
    layer=Image.new('RGBA',(100,60),'white')
    small,pos=animated_balloon(layer,(20,30),0,True)
    assert small.size==(72,43) and pos==(34,38)
    assert animated_balloon(layer,(20,30),0,False)==(layer,(20,30))
    assert animated_balloon(layer,(20,30),1,True)==(layer,(20,30))


def test_recorded_page_turns_cycle_and_stay_in_transition(tmp_path):
    import wave
    from services.comic_turn_audio import recorded_page_turns
    paths=[]
    for i in range(4):
        path=tmp_path/f'turn-{i}.wav';paths.append(path)
        with wave.open(str(path),'wb') as sound:
            sound.setparams((1,2,44100,0,'NONE','not compressed'))
            sound.writeframes(np.full(44100,3000*(i+1),dtype=np.int16).tobytes())
    pages=[{'end':i*2+1} for i in range(13)]
    tracks,resources=recorded_page_turns(paths,pages,.7,.5)
    try:
        assert len(tracks)==12
        for i,track in enumerate(tracks):
            assert track.start==pages[i]['end'] and track.duration==.7
            assert np.allclose(track.get_frame(.2),tracks[i%4].get_frame(.2))
        assert float(np.mean(tracks[0].get_frame(.2))) < float(np.mean(tracks[3].get_frame(.2)))
    finally:
        for resource in resources:resource.close()


def test_turn_sound_and_background_mix(tmp_path):
    from moviepy import AudioClip, VideoFileClip
    paths = fixtures(tmp_path)
    voice = str(tmp_path / 'voice.wav')
    clip = AudioClip(lambda t: .05 * np.sin(2 * np.pi * 220 * np.asarray(t)), duration=3, fps=44100)
    clip.write_audiofile(voice, logger=None); clip.close()
    settings = {'comic': {'version':1,'mode':'comic','turn_duration':.5,'turn_sound':True},
                'bgm_path': voice, 'bgm_volume':0}
    result = render_comic(temp_dir=str(tmp_path), images=paths, durations=[1,1,1], audio_path=voice,
        subtitles=[], settings=settings, resolution=(320,180),
        sfx_cues=[{'path':voice,'start':2.1,'duration':.2,'volume_db':-6}])
    with VideoFileClip(result) as movie:
        assert np.abs(movie.audio.to_soundarray(tt=np.arange(2.15,2.35,1/44100))).max() > .005
