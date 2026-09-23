import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from services.comic_render_service import ComicFrames, LAYOUTS, build_timeline, comic_enabled, page_curl, render_comic

FONT = str(Path('auth-web/public/fonts/NanumSquareExtraBold.ttf').resolve())


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
    assert half[30, 85].mean() > 150  # lit paper back
    assert half[30, 150, 2] > 150  # revealed next page


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
