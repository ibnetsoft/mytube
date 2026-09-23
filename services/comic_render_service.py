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

LAYOUTS = {
    'spread': [[.025,.04,.465,.92],[.51,.04,.465,.92]],
    'single': [[.025,.04,.95,.92]],
    'grid': [[.025,.04,.465,.44],[.51,.04,.465,.44],[.025,.52,.465,.44],[.51,.52,.465,.44]],
    'inset': [[.025,.04,.95,.92],[.65,.07,.30,.43]],
}
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


def build_timeline(durations, panel_count, turn_duration):
    if not durations or any(not math.isfinite(float(d)) or float(d) <= 0 for d in durations):
        raise ValueError('만화책 씬의 재생 시간이 올바르지 않습니다.')
    starts = [0.0]
    for duration in durations:
        starts.append(starts[-1] + float(duration))
    pages = []
    for first in range(0, len(durations), panel_count):
        last = min(first + panel_count, len(durations))
        index = len(pages)
        pages.append(dict(first=first, last=last, source_start=starts[first], source_end=starts[last],
                          start=starts[first] + index * turn_duration,
                          end=starts[last] + index * turn_duration))
    return starts, pages, pages[-1]['end']


def page_curl(previous, following, progress):
    """Cylindrical fold: mapped front, shaded paper back, cast shadow.

    Both complete pages (including balloons) are textures. Exact endpoint frames
    avoid a flash at the cut. This is a stylized full-sheet turn, not a dissolve.
    """
    if progress <= 0:
        return previous.copy()
    if progress >= 1:
        return following.copy()
    h, w = previous.shape[:2]
    p = progress * progress * (3 - 2 * progress)
    radius = max(2., w * .09 * math.sin(math.pi * progress))
    fold = w * (1 - p)
    xs = np.arange(w, dtype=float)
    out = following.astype(float).copy()
    shadow = np.exp(-np.maximum(0, xs - fold) / max(1., radius * .65)) * .24
    out *= (1 - np.where(xs >= fold, shadow, 0))[None, :, None]
    flat = xs < fold - radius
    out[:, flat] = previous[:, flat]
    bent = (xs >= fold - radius) & (xs < fold)
    u = np.clip((xs[bent] - (fold - radius)) / radius, 0, 1)
    source = np.clip((fold - radius + np.arcsin(u) * radius).astype(int), 0, w - 1)
    out[:, bent] = previous[:, source] * (1 - .32 * u)[None, :, None]
    back = (xs >= fold) & (xs < fold + radius)
    u = (xs[back] - fold) / radius
    shade = .70 + .28 * np.sin(u * math.pi)
    out[:, back] = np.array([249, 245, 232])[None, None, :] * shade[None, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


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


def balloon_layer(size, blocks, font_path, font_size, position='bottom'):
    """Pre-layout all balloons so earlier ones never move as later ones appear.

    Fail explicitly on overflow; never clip or silently drop dialogue.
    """
    w, h = size
    pad = max(5, round(w * .025))
    bw = w - pad * 4
    font_size = min(font_size, max(12, int(w / 12)))
    draw = ImageDraw.Draw(Image.new('RGB', size))
    while True:
        font = ImageFont.truetype(font_path, font_size)
        line_h = math.ceil(font_size * 1.3)
        lines = [wrap_text(draw, b.get('text', ''), font, bw - pad * 2) for b in blocks]
        heights = [max(line_h, len(ls) * line_h) + pad * 2 for ls in lines]
        total = sum(heights) + max(0, len(blocks) - 1) * pad * 2
        if total <= h * .84 or not blocks:
            break
        if font_size <= 12:
            raise ValueError('말풍선이 컷을 넘칩니다. 대사를 줄이거나 전체 1컷 레이아웃을 선택해 주세요.')
        font_size -= 1
    y = pad * 2 if position == 'top' else h - total - pad * 2
    result = []
    for block, ls, bh in zip(blocks, lines, heights):
        layer = Image.new('RGBA', size)
        d = ImageDraw.Draw(layer)
        x = pad * 2
        d.rounded_rectangle((x, y, x + bw, y + bh), radius=pad * 2, fill='white', outline='#252525', width=max(1, pad // 3))
        d.polygon([(x + pad * 3, y + bh - 2), (x + pad * 5, y + bh - 2), (x + pad * 3, y + bh + pad)], fill='white')
        d.line([(x + pad * 3, y + bh), (x + pad * 3, y + bh + pad), (x + pad * 5, y + bh)], fill='#252525', width=max(1, pad // 3))
        for line_index, line in enumerate(ls):
            d.text((x + pad, y + pad + line_index * line_h), line, font=font, fill='#171717', stroke_width=0)
        bounds = layer.getbbox()
        result.append((float(block.get('start', block.get('start_time', 0))), layer.crop(bounds), bounds[:2]))
        y += bh + pad * 2
    return result


class ComicFrames:
    def __init__(self, images, durations, subtitles, settings, resolution, font_path, scene_numbers=None):
        from moviepy import VideoFileClip
        self.options = settings['comic']
        self.mode = self.options['mode']
        self.layout = LAYOUTS.get(self.options.get('layout'), LAYOUTS['spread'])
        self.turn = _number(self.options.get('turn_duration'), .7, .3, 1.5)
        self.starts, self.pages, self.duration = build_timeline(durations, len(self.layout), self.turn)
        self.resolution = tuple(resolution)
        self.media = []
        self.balloons = []
        self.panel_options = []
        self._cache = {}
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
                        self.media.append(ImageOps.exif_transpose(image).convert('RGB'))
                number = (scene_numbers or list(range(1, len(images) + 1)))[i]
                option = (self.options.get('panels') or {}).get(str(number), {})
                self.panel_options.append(option)
                blocks = [s for s in subtitles if self.starts[i] <= float(s.get('start', s.get('start_time', 0))) < self.starts[i + 1]]
                rect = self.layout[i % len(self.layout)]
                size = (round(rect[2] * resolution[0]), round(rect[3] * resolution[1]))
                self.balloons.append(balloon_layer(size, blocks, font_path,
                    round(_number(self.options.get('font_size'), 28, 18, 44) * resolution[0] / 1280), option.get('bubble_position', 'bottom')))
        except Exception:
            self.close()
            raise

    def close(self):
        for clip in self._clips.values():
            clip.close()
        self._clips.clear()
        for media in self.media:
            if hasattr(media, 'close'):
                media.close()

    def page(self, index, source_time, all_balloons=False):
        page = self.pages[index]
        from moviepy import VideoFileClip
        for key in list(self._clips):
            if key < page['first'] or key >= page['last']:
                self._clips.pop(key).close()
        w, h = self.resolution
        canvas = Image.new('RGB', (w, h), '#f7f2e8')
        d = ImageDraw.Draw(canvas)
        if len(self.layout) == 2 and self.options.get('layout', 'spread') == 'spread':
            d.line([(w // 2, int(h * .02)), (w // 2, int(h * .98))], fill='#c8bfae', width=max(1, w // 640))
        for slot, scene_index in enumerate(range(page['first'], page['last'])):
            rect = self.layout[slot]
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
            if option.get('fit') == 'cover':
                panel = ImageOps.fit(frame, (pw, ph), method=Image.Resampling.LANCZOS)
            else:
                fitted = ImageOps.contain(frame, (pw, ph), method=Image.Resampling.LANCZOS)
                panel = Image.new('RGB', (pw, ph), '#ebe5d9')
                panel.paste(fitted, ((pw - fitted.width) // 2, (ph - fitted.height) // 2))
            if self.options.get('dim_inactive') and not all_balloons and not self.starts[scene_index] <= source_time < self.starts[scene_index + 1]:
                panel = Image.blend(panel, Image.new('RGB', panel.size), .22)
            for start, balloon, position in self.balloons[scene_index]:
                if all_balloons or source_time >= start:
                    panel.paste(balloon, position, balloon)
            canvas.paste(panel, (x, y))
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
            # Deterministic low-volume paper-like rustle; no external audio dependency.
            for page in frames.pages[:-1]:
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
