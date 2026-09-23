"""Opt-in landscape comic compositor. Standard slideshow rendering never imports this path.

Scene media and narration keep their original timebase. Silent page-turn intervals
are inserted between pages; narration and SFX are remapped using the same segments.
"""
import bisect
import json
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from services.comic_layouts import LAYOUTS
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v'}


def comic_enabled(settings):
    value = (settings or {}).get('comic') or {}
    return isinstance(value, dict) and value.get('version') == 1 and value.get('mode') in ('comic', 'moving_comic')


def _number(value, fallback, low, high):
    try:
        value = float(value)
        return max(low, min(high, value)) if math.isfinite(value) else fallback
    except (TypeError, ValueError):
        return fallback


def build_timeline(durations, panel_count, turn_duration, page_layouts=None, default_layout=None):
    if not durations or any(not math.isfinite(float(d)) or float(d) <= 0 for d in durations):
        raise ValueError('만화책 씬의 재생 시간이 올바르지 않습니다.')
    starts = [0.0]
    for duration in durations:
        starts.append(starts[-1] + float(duration))
    pages = []
    first = 0
    while first < len(durations):
        index = len(pages)
        layout = (page_layouts or {}).get(str(index), default_layout)
        count = len(LAYOUTS[layout]) if layout in LAYOUTS else panel_count
        last = min(first + count, len(durations))
        pages.append(dict(first=first, last=last, source_start=starts[first], source_end=starts[last],
                          start=starts[first] + index * turn_duration,
                          end=starts[last] + index * turn_duration))
        if default_layout: pages[-1]['layout'] = layout if layout in LAYOUTS else default_layout
        first = last
    return starts, pages, pages[-1]['end']


from services.comic_page_turn import page_curl


def wrap_text(draw, text, font, width):
    lines = []
    for paragraph in str(text).split('\n'):
        line = ''
        for char in paragraph:
            if line and draw.textlength(line + char, font=font) > width:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    return lines


from services.comic_lettering import caption_layers as balloon_layer

def balloon_pop_scale(elapsed):
    """Bounded bounce: never grow beyond the approved lettering footprint."""
    t = max(0., min(1., elapsed / .36))
    if t < .55:
        return .72 + .28 * (1 - (1 - t / .55) ** 3)
    if t < .78:
        return 1 - .055 * math.sin((t - .55) / .23 * math.pi / 2)
    return .945 + .055 * math.sin((t - .78) / .22 * math.pi / 2)

def animated_balloon(layer, position, elapsed, animate):
    if not animate or elapsed >= .36:
        return layer, position
    scale = balloon_pop_scale(elapsed)
    width, height = layer.size
    resized = layer.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS)
    return resized, (position[0] + (width-resized.width)//2, position[1] + (height-resized.height)//2)


class ComicFrames:
    def __init__(self, images, durations, subtitles, settings, resolution, font_path, scene_numbers=None):
        from moviepy import VideoFileClip
        self.options = settings['comic']
        self.mode = self.options['mode']
        self.layout = LAYOUTS.get(self.options.get('layout'), LAYOUTS['spread'])
        self.turn = _number(self.options.get('turn_duration'), .7, .3, 1.5)
        self.starts, self.pages, self.duration = build_timeline(durations, len(self.layout), self.turn, self.options.get('page_layouts'), self.options.get('layout','spread'))
        self.resolution = tuple(resolution)
        self.media = []
        self.balloons = []
        self.balloon_kinds = []
        self.panel_options = []
        self._cache = {}
        self._panel_cache = {}
        self._clips = {}
        try:
            for i, path in enumerate(images):
                if not path or not os.path.isfile(path):
                    raise ValueError(f'만화책 컷 {i + 1}의 이미지 또는 영상이 없습니다.')
                if Path(path).suffix.lower() in VIDEO_EXTENSIONS:
                    if self.mode == 'comic':
                        clip = VideoFileClip(path, audio=False)
                        frame = Image.fromarray(clip.get_frame(0))
                        clip.close()
                        self.media.append(frame)
                    else:
                        self.media.append(path)
                else:
                    with Image.open(path) as image:
                        self.media.append(ImageOps.exif_transpose(image).convert('RGBA'))
                number = (scene_numbers or list(range(1, len(images) + 1)))[i]
                option = (self.options.get('panels') or {}).get(str(number), {})
                self.panel_options.append(option)
                blocks = [s for s in subtitles if self.starts[i] <= float(s.get('start', s.get('start_time', 0))) < self.starts[i + 1]]
                page = next(p for p in self.pages if p['first'] <= i < p['last'])
                rect = LAYOUTS[page['layout']][i-page['first']]
                default_letter = {}
                if page['layout']=='diagonal': default_letter={'x':.05 if i==page['first'] else .55,'y':.05 if i==page['first'] else .68,'width':.4}
                blocks = [{**b, 'comic': (self.options.get('lettering') or {}).get(f'{number}:{j}', b.get('comic', default_letter))} for j,b in enumerate(blocks)]
                self.balloon_kinds.append([(b.get('comic') or {}).get('kind') or b.get('dialogue_kind') or 'narration' for b in blocks])
                size = (round(rect[2] * resolution[0]), round(rect[3] * resolution[1]))
                self.balloons.append(balloon_layer(size, blocks, font_path,
                    round(_number(self.options.get('font_size'), 28, 18, 44) * resolution[0] / 1280), option.get('bubble_position', 'bottom')))
                if page['layout']=='diagonal':
                    for _, layer, (lx,ly) in self.balloons[-1]:
                        yy,xx=np.nonzero(np.asarray(layer.getchannel('A')))
                        sums=(xx+lx)/size[0]+(yy+ly)/size[1]
                        if len(sums) and (sums.max()>1 if i==page['first'] else sums.min()<1.01):
                            raise ValueError('문구가 대각선 컷 경계를 넘습니다. 위치나 폭을 조정해 주세요.')
        except Exception:
            self.close()
            raise

    def close(self):
        for clip in self._clips.values():
            clip.close()
        self._clips.clear()
        self._panel_cache.clear()
        for media in self.media:
            if hasattr(media, 'close'):
                media.close()

    def page(self, index, source_time, all_balloons=False):
        page = self.pages[index]
        self._panel_cache = {key:value for key,value in self._panel_cache.items() if page['first']<=key<page['last']}
        from moviepy import VideoFileClip
        for key in list(self._clips):
            if key < page['first'] or key >= page['last']:
                self._clips.pop(key).close()
        layout_name = page['layout']
        layout = LAYOUTS[layout_name]
        w, h = self.resolution
        canvas = Image.new('RGB', (w, h), '#f7f2e8')
        d = ImageDraw.Draw(canvas)
        if layout_name in ('spread','double'):
            d.line([(w // 2, int(h * .02)), (w // 2, int(h * .98))], fill='#c8bfae', width=max(1, w // 640))
        for slot, scene_index in enumerate(range(page['first'], page['last'])):
            rect = layout[slot]
            x, y, pw, ph = [round(v * (w if j % 2 == 0 else h)) for j, v in enumerate(rect)]
            media = self.media[scene_index]
            if isinstance(media, str):
                if scene_index not in self._clips:
                    self._clips[scene_index] = VideoFileClip(media, audio=False)
                media = self._clips[scene_index]
            if isinstance(media, Image.Image):
                frame = media
            else:
                local_time = max(0, min(source_time - self.starts[scene_index],
                    self.starts[scene_index + 1] - self.starts[scene_index], max(0, media.duration - 1 / max(1, media.fps))))
                frame = Image.fromarray(media.get_frame(local_time))
            option = self.panel_options[scene_index]
            if isinstance(media, Image.Image) and scene_index in self._panel_cache:
                panel=self._panel_cache[scene_index].copy()
            elif option.get('fit') == 'cover':
                panel = ImageOps.fit(frame, (pw, ph), method=Image.Resampling.LANCZOS)
            else:
                fitted = ImageOps.contain(frame, (pw, ph), method=Image.Resampling.LANCZOS)
                panel = Image.new('RGB', (pw, ph), '#ebe5d9')
                panel.paste(fitted, ((pw - fitted.width) // 2, (ph - fitted.height) // 2))
            if isinstance(media, Image.Image) and scene_index not in self._panel_cache:
                self._panel_cache[scene_index]=panel.copy()
            if option.get('motion')=='pan' and isinstance(media, Image.Image):
                progress=max(0,min(1,(source_time-self.starts[scene_index])/(self.starts[scene_index+1]-self.starts[scene_index])))
                zoom=1+.07*progress
                panel=ImageOps.fit(panel.resize((round(pw*zoom),round(ph*zoom)),Image.Resampling.LANCZOS),(pw,ph))
            if self.options.get('dim_inactive') and not all_balloons and not self.starts[scene_index] <= source_time < self.starts[scene_index + 1]:
                panel = Image.blend(panel, Image.new('RGB', panel.size), .22)
            for bi, (start, balloon, position) in enumerate(self.balloons[scene_index]):
                if all_balloons or source_time >= start:
                    balloon, position = animated_balloon(balloon, position, source_time-start, not all_balloons and self.balloon_kinds[scene_index][bi]=='dialogue')
                    panel.paste(balloon, position, balloon)
            if layout_name == 'diagonal':
                points = [(0,0),(pw-1,0),(0,ph-1)] if slot == 0 else [(pw-1,5),(pw-1,ph-1),(5,ph-1)]
                mask = Image.new('L',(pw,ph)); ImageDraw.Draw(mask).polygon(points,fill=255)
                canvas.paste(panel,(x,y),mask)
                d.line([(x+px,y+py) for px,py in points+[points[0]]],fill='#222',width=2)
            elif layout_name == 'breakout' and slot == 1:
                if not isinstance(frame,Image.Image) or frame.mode != 'RGBA' or frame.getchannel('A').getextrema()[0] == 255:
                    raise ValueError('경계 돌파형의 두 번째 컷은 배경이 투명한 PNG 전경이 필요합니다.')
                foreground=ImageOps.contain(frame,(pw,ph),method=Image.Resampling.LANCZOS)
                canvas.paste(foreground,(x+(pw-foreground.width)//2,y+(ph-foreground.height)//2),foreground)
                for bi, (start, balloon, position) in enumerate(self.balloons[scene_index]):
                    if all_balloons or source_time >= start:
                        balloon, position = animated_balloon(balloon, position, source_time-start, not all_balloons and self.balloon_kinds[scene_index][bi]=='dialogue')
                        canvas.paste(balloon,(x+position[0],y+position[1]),balloon)
            else:
                canvas.paste(panel, (x, y))
                if layout_name not in ('borderless','bleed','double'):
                    d.rectangle((x, y, x + pw - 1, y + ph - 1), outline='#222222', width=max(2, round(w / 640)))
        return np.asarray(canvas)

    def frame(self, t):
        index = min(len(self.pages) - 1, max(0, bisect.bisect_right([p['start'] for p in self.pages], t) - 1))
        page = self.pages[index]
        if t >= page['end'] and index + 1 < len(self.pages):
            if self._cache.get('index') != index:
                self._cache = {'index': index, 'previous': self.page(index, page['source_end'] - .0001),
                               'next': self.page(index + 1, self.pages[index + 1]['source_start'] - .0001)}
            return page_curl(self._cache['previous'], self._cache['next'], (t - page['end']) / self.turn)
        return self.page(index, min(page['source_end'] - .0001, page['source_start'] + t - page['start']))


def render_comic(*, temp_dir, images, durations, audio_path, subtitles, settings, resolution, scene_numbers=None, sfx_cues=None, progress_callback=None):
    from moviepy import AudioFileClip, AudioClip, CompositeAudioClip, VideoClip, afx
    from services.ffmpeg_slideshow_service import _prepare_fonts_dir, _resolve_audio_asset
    progress = progress_callback or (lambda *_: None)
    if not comic_enabled(settings):
        raise ValueError('만화책 모드 설정이 없습니다.')
    if resolution[0] <= resolution[1]:
        raise ValueError('만화책 모드는 가로 화면만 지원합니다.')
    font_settings = dict(settings)
    font_settings['subtitle_font_family'] = 'NanumSquareExtraBold'
    fonts_dir = _prepare_fonts_dir(temp_dir, font_settings)
    fonts = sorted(Path(fonts_dir).glob('*.ttf')) + sorted(Path(fonts_dir).glob('*.otf'))
    if not fonts:
        raise ValueError('말풍선을 렌더링할 한글 폰트가 없습니다.')
    frames = ComicFrames(images, durations, subtitles, settings, resolution, str(fonts[0]), scene_numbers)
    resources = []
    video = None
    try:
        # Persist printable full pages next to the movie for worker/package consumers.
        page_dir = Path(temp_dir) / 'comic_pages'
        page_dir.mkdir(exist_ok=True)
        for index, page in enumerate(frames.pages):
            Image.fromarray(frames.page(index, page['source_end'] - .0001, True)).save(page_dir / f'page_{index + 1:03}.png')
        narration = AudioFileClip(audio_path)
        resources.append(narration)
        tracks = []
        for page in frames.pages:
            end = min(page['source_end'], narration.duration)
            if end > page['source_start']:
                tracks.append(narration.subclipped(page['source_start'], end).with_start(page['start']))
        bgm_path = _resolve_audio_asset(temp_dir, settings.get('bgm_path'))
        if bgm_path:
            bgm = AudioFileClip(bgm_path)
            resources.append(bgm)
            if settings.get('bgm_loop', True):
                bgm = bgm.with_effects([afx.AudioLoop(duration=frames.duration)])
            tracks.append(bgm.with_volume_scaled(_number(settings.get('bgm_volume'), .08, 0, 1)))
        for cue in sfx_cues or []:
            path = _resolve_audio_asset(temp_dir, cue.get('path') or cue.get('relative_path') or cue.get('filename'))
            if not path or cue.get('enabled') is False:
                continue
            effect = AudioFileClip(path)
            resources.append(effect)
            start = _number(cue.get('start', cue.get('time', 0)), 0, 0, frames.starts[-1])
            page_index = min(len(frames.pages) - 1, bisect.bisect_right([p['source_start'] for p in frames.pages], start) - 1)
            length = min(effect.duration, _number(cue.get('duration'), effect.duration, .1, 30))
            tracks.append(effect.subclipped(0, length).with_start(start + page_index * frames.turn)
                .with_volume_scaled(10 ** (_number(cue.get('volume_db'), -18, -60, 12) / 20)))
        if settings['comic'].get('turn_sound', True):
            recordings=settings['comic'].get('turn_sound_paths') or []
            if recordings:
                from services.comic_turn_audio import recorded_page_turns
                paths=[_resolve_audio_asset(temp_dir,value) for value in recordings]
                if not all(paths):raise ValueError('책장 넘김 효과음 파일을 찾을 수 없습니다.')
                sounds,opened=recorded_page_turns(paths,frames.pages,frames.turn,
                    _number(settings['comic'].get('turn_sound_volume'),.55,0,1))
                resources.extend(opened);tracks.extend(sounds)
            # Deterministic low-volume paper-like rustle; no external audio dependency.
            for page in ([] if recordings else frames.pages[:-1]):
                duration = frames.turn
                def rustle(t, duration=duration):
                    t = np.asarray(t)
                    signal = np.sin(t * 19013 + np.sin(t * 2171) * 8) * np.sin(np.pi * np.clip(t / duration, 0, 1)) ** 2 * .045
                    return np.stack([signal, signal], axis=-1)
                tracks.append(AudioClip(rustle, duration=duration, fps=44100).with_start(page['end']))
        audio = CompositeAudioClip(tracks).with_duration(frames.duration)
        resources.append(audio)
        video = VideoClip(frames.frame, duration=frames.duration).with_audio(audio)
        output = str(Path(temp_dir) / 'output.mp4')
        progress(45, '만화책 페이지와 말풍선 렌더링 중...')
        from proglog import ProgressBarLogger
        class ComicProgress(ProgressBarLogger):
            last_percent = -1
            def bars_callback(self, bar, attr, value, old_value=None):
                if bar != 'frame_index' or attr != 'index':
                    return
                total = self.bars.get(bar, {}).get('total') or 1
                percent = 45 + int(40 * value / total)
                if percent != self.last_percent:
                    self.last_percent = percent
                    progress(percent, '만화책 페이지와 말풍선 렌더링 중...')
        video.write_videofile(output, fps=24, codec='libx264', audio_codec='aac', preset='veryfast',
            temp_audiofile=str(Path(temp_dir) / 'comic_audio.m4a'), threads=2, logger=ComicProgress(),
            ffmpeg_params=['-pix_fmt', 'yuv420p', '-movflags', '+faststart'])
        Path(temp_dir, 'comic_manifest.json').write_text(json.dumps({'version': 1, 'mode': frames.mode,
            'duration': frames.duration, 'pages': frames.pages}, ensure_ascii=False, indent=2), encoding='utf-8')
        progress(88, '만화책 영상 생성 완료')
        return output
    finally:
        if video:
            video.close()
        for resource in reversed(resources):
            resource.close()
        frames.close()
