import os
import re
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path


class FastRenderUnsupported(RuntimeError):
    pass


class FastRenderTimeout(RuntimeError):
    pass


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _ffmpeg_executable():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _media_duration(ffmpeg_exe, path):
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", "-i", path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
        if not match:
            return 0.0
        return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    except Exception:
        return 0.0


def _ass_time(seconds):
    value = max(0.0, float(seconds or 0.0))
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = value % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _ass_color(value, alpha=0):
    raw = str(value or "#ffffff").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    raw = (raw + "ffffff")[:6]
    try:
        red, green, blue = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        red, green, blue = 255, 255, 255
    return f"&H{max(0, min(255, int(alpha))):02X}{blue:02X}{green:02X}{red:02X}"


def _ass_text(value):
    return (
        str(value or "")
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", r"\N")
        .replace("\n", r"\N")
        .replace("\r", r"\N")
    )


def _setting(settings, *keys, default=None):
    for key in keys:
        if settings.get(key) is not None:
            return settings.get(key)
    return default


def _write_ass_file(path, subtitles, settings, resolution):
    width, height = resolution
    font_name = str(_setting(
        settings,
        "subtitle_font_family",
        "subtitle_font",
        "font",
        default="Malgun Gothic",
    ))
    font_name = {
        "ChosunIlboMyungjo": "Chosun_ilbo_myungjottf",
        "CookieRun-Regular": "CookieRun",
        "NetmarbleB": "netmarble",
        "NotoSansJP": "Noto Sans CJK JP",
        "Pretendard-Bold": "Pretendard",
        "S-CoreDream-6Bold": "S-Core Dream",
    }.get(font_name, font_name)

    font_value = float(_setting(settings, "subtitle_font_size", "font_size", default=5.0) or 5.0)
    font_size = int(width * font_value / 100.0) if 0.1 <= font_value <= 20 else int(font_value)
    font_size = max(12, font_size)
    primary = _ass_color(_setting(
        settings,
        "subtitle_text_color",
        "subtitle_base_color",
        "font_color",
        default="#ffffff",
    ))
    outline = _ass_color(_setting(settings, "subtitle_stroke_color", "stroke_color", default="#000000"))
    outline_width = float(_setting(settings, "subtitle_stroke_width", "stroke_width", default=0) or 0)
    outline_width *= height / 360.0

    bg_enabled = bool(int(_setting(settings, "subtitle_bg_enabled", "bg_enabled", default=0) or 0))
    bg_opacity = max(0.0, min(1.0, float(_setting(settings, "subtitle_bg_opacity", "bg_opacity", default=0.5) or 0.5)))
    back_alpha = int((1.0 - bg_opacity) * 255) if bg_enabled else 255
    back = _ass_color(_setting(settings, "subtitle_bg_color", "bg_color", default="#000000"), back_alpha)
    border_style = 3 if bg_enabled else 1

    raw_position = str(_setting(settings, "subtitle_pos_y", "pos_y", default="b:12%") or "b:12%")
    match = re.search(r"(-?\d+(?:\.\d+)?)", raw_position)
    position_value = float(match.group(1)) if match else 12.0
    if raw_position.startswith("b:") or "%" in raw_position or abs(position_value) <= 100:
        margin_v = int(height * max(0.0, min(90.0, position_value)) / 100.0)
    else:
        margin_v = max(0, int(position_value))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary},{primary},{outline},{back},0,0,0,0,100,100,0,0,{border_style},{outline_width:.2f},0,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for subtitle in subtitles or []:
        start = float(subtitle.get("start") or 0.0)
        end = float(subtitle.get("end") or start)
        text = _ass_text(subtitle.get("text"))
        if text and end > start:
            events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}")
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


def _prepare_fonts_dir(temp_dir, settings):
    font_name = str(_setting(
        settings,
        "subtitle_font_family",
        "subtitle_font",
        "font",
        default="Malgun Gothic",
    ))
    aliases = {
        "GmarketSans": ["GmarketSansTTFBold.ttf", "GmarketSansBold.woff"],
        "GmarketSansBold": ["GmarketSansTTFBold.ttf", "GmarketSansBold.woff"],
        "ChosunIlboMyungjo": ["ChosunIlboMyungjo.ttf", "Chosunilbo_myungjo.woff"],
        "NotoSansJP": ["NotoSansJP-Bold.ttf", "NotoSansJP-Regular.ttf"],
        "CookieRun-Regular": ["CookieRun-Regular.woff"],
    }
    family_overrides = {
        "BinggraeMelona-Bold": "BinggraeMelona-Bold",
        "GmarketSans": "GmarketSansBold",
        "GmarketSansBold": "GmarketSansBold",
        "Jalnan": "Jalnan",
        "MapoFlowerIsland": "MapoFlowerIsland",
    }
    candidates = aliases.get(font_name, [font_name])
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    source_dirs = [
        os.path.join(root_dir, "static", "fonts"),
        os.path.join(root_dir, "auth-web", "public", "fonts"),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
    ]
    fonts_dir = os.path.join(temp_dir, "fast_render_fonts")
    os.makedirs(fonts_dir, exist_ok=True)
    for candidate in candidates:
        for source_dir in source_dirs:
            source_path = os.path.join(source_dir, candidate)
            if os.path.isfile(source_path):
                destination = os.path.join(fonts_dir, os.path.basename(source_path))
                if source_path.lower().endswith(".woff"):
                    destination = os.path.splitext(destination)[0] + ".ttf"
                    _convert_woff_to_ttf(source_path, destination)
                else:
                    shutil.copy2(source_path, destination)
                if font_name in family_overrides:
                    _rewrite_sfnt_family_name(destination, family_overrides[font_name])
                return fonts_dir
    return os.path.join(root_dir, "static", "fonts")


def _convert_woff_to_ttf(source_path, destination_path):
    data = Path(source_path).read_bytes()
    if len(data) < 44 or data[:4] != b"wOFF":
        raise FastRenderUnsupported(f"지원하지 않는 웹폰트 형식입니다: {source_path}")

    flavor = data[4:8]
    num_tables = struct.unpack_from(">H", data, 12)[0]
    max_power = 1 << (num_tables.bit_length() - 1)
    search_range = max_power * 16
    entry_selector = max_power.bit_length() - 1
    range_shift = num_tables * 16 - search_range
    output = bytearray(struct.pack(">4sHHHH", flavor, num_tables, search_range, entry_selector, range_shift))
    records = []
    table_data = bytearray()
    table_offset = 12 + num_tables * 16

    for index in range(num_tables):
        entry_offset = 44 + index * 20
        tag, offset, compressed_length, original_length, checksum = struct.unpack_from(
            ">4sLLLL", data, entry_offset
        )
        raw = data[offset:offset + compressed_length]
        if compressed_length < original_length:
            raw = zlib.decompress(raw)
        if len(raw) != original_length:
            raise FastRenderUnsupported(f"웹폰트 테이블을 복원할 수 없습니다: {source_path}")
        records.append((tag, checksum, table_offset, original_length))
        table_data.extend(raw)
        padding = (-len(raw)) % 4
        if padding:
            table_data.extend(b"\0" * padding)
        table_offset += len(raw) + padding

    for record in records:
        output.extend(struct.pack(">4sLLL", *record))
    output.extend(table_data)
    Path(destination_path).write_bytes(output)


def _sfnt_checksum(data):
    padded = data + (b"\0" * ((-len(data)) % 4))
    return sum(struct.unpack(f">{len(padded) // 4}L", padded)) & 0xFFFFFFFF


def _rewrite_sfnt_family_name(path, family_name):
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] == b"wOFF":
        return
    num_tables = struct.unpack_from(">H", data, 4)[0]
    tables = {}
    for index in range(num_tables):
        tag, _checksum, offset, length = struct.unpack_from(">4sLLL", data, 12 + index * 16)
        tables[tag] = bytearray(data[offset:offset + length])
    name_table = tables.get(b"name")
    if not name_table or len(name_table) < 6:
        return

    _format, count, string_offset = struct.unpack_from(">HHH", name_table, 0)
    names = []
    replaced_ids = {1, 4, 16}
    for index in range(count):
        platform, encoding, language, name_id, length, offset = struct.unpack_from(
            ">HHHHHH", name_table, 6 + index * 12
        )
        if name_id in replaced_ids:
            continue
        raw = bytes(name_table[string_offset + offset:string_offset + offset + length])
        names.append((platform, encoding, language, name_id, raw))

    mac_name = family_name.encode("latin-1", errors="replace")
    windows_name = family_name.encode("utf-16-be")
    names.extend([
        (1, 0, 0, 1, mac_name),
        (1, 0, 0, 4, mac_name),
        (3, 1, 0x0409, 1, windows_name),
        (3, 1, 0x0409, 4, windows_name),
        (3, 1, 0x0409, 16, windows_name),
    ])
    names.sort(key=lambda item: item[:4])
    storage = bytearray()
    records = bytearray()
    for platform, encoding, language, name_id, raw in names:
        records.extend(struct.pack(">HHHHHH", platform, encoding, language, name_id, len(raw), len(storage)))
        storage.extend(raw)
    tables[b"name"] = bytearray(struct.pack(">HHH", 0, len(names), 6 + len(records)) + records + storage)

    if b"head" in tables and len(tables[b"head"]) >= 12:
        tables[b"head"][8:12] = b"\0\0\0\0"
    tags = sorted(tables)
    max_power = 1 << (len(tags).bit_length() - 1)
    search_range = max_power * 16
    entry_selector = max_power.bit_length() - 1
    range_shift = len(tags) * 16 - search_range
    output = bytearray(struct.pack(">4sHHHH", data[:4], len(tags), search_range, entry_selector, range_shift))
    table_offset = 12 + len(tags) * 16
    body = bytearray()
    offsets = {}
    for tag in tags:
        raw = bytes(tables[tag])
        offsets[tag] = table_offset
        output.extend(struct.pack(">4sLLL", tag, _sfnt_checksum(raw), table_offset, len(raw)))
        body.extend(raw)
        padding = (-len(raw)) % 4
        if padding:
            body.extend(b"\0" * padding)
        table_offset += len(raw) + padding
    output.extend(body)
    if b"head" in offsets:
        adjustment = (0xB1B0AFBA - _sfnt_checksum(bytes(output))) & 0xFFFFFFFF
        struct.pack_into(">L", output, offsets[b"head"] + 8, adjustment)
    Path(path).write_bytes(output)


def _filter_path(path):
    value = os.path.abspath(path).replace("\\", "/")
    value = value.replace(":", r"\:").replace("'", r"\'")
    return value


def _transition_name(value):
    normalized = str(value or "").strip().lower().replace(" ", "_")
    return {
        "": "fade",
        "none": "fade",
        "dissolve": "dissolve",
        "darken": "fadeblack",
        "brighten": "fadewhite",
        "white_fade": "fadewhite",
        "black_fade": "fadeblack",
        "wipe_left": "wipeleft",
        "wipe_right": "wiperight",
        "wipe_up": "wipeup",
        "wipe_down": "wipedown",
        "push": "slideleft",
        "zoom": "zoomin",
        "focus": "radial",
        "circle_spread": "circleopen",
        "mosaic": "pixelize",
        "diagonal_wipe": "diagtl",
    }.get(normalized, "fade")


def _image_filter(input_index, output_label, width, height, fps, duration, effect):
    normalized = str(effect or "auto_classify").strip().lower().replace(" ", "_")
    base = (
        f"[{input_index}:v]scale={int(width * 1.12)}:{int(height * 1.12)}:"
        f"force_original_aspect_ratio=increase,crop={int(width * 1.12)}:{int(height * 1.12)}"
    )
    frames = max(1, int(duration * fps))
    if normalized in {"none", "static"}:
        return (
            f"{base},scale={width}:{height},fps={fps},trim=duration={duration:.3f},"
            f"setsar=1,format=yuv420p[{output_label}]"
        )
    if normalized in {"zoom_out"}:
        zoom = "if(eq(on,0),1.10,max(1.0,pzoom-0.00035))"
        x_pos = "iw/2-(iw/zoom/2)"
        y_pos = "ih/2-(ih/zoom/2)"
    elif normalized in {"pan_left", "pan_right"}:
        zoom = "1.10"
        progress = f"min(1,on/{frames})"
        x_pos = f"(iw-iw/zoom)*{progress}" if normalized == "pan_right" else f"(iw-iw/zoom)*(1-{progress})"
        y_pos = "ih/2-(ih/zoom/2)"
    elif normalized in {"pan_up", "scroll_up", "pan_down", "scroll_down"}:
        zoom = "1.10"
        progress = f"min(1,on/{frames})"
        x_pos = "iw/2-(iw/zoom/2)"
        y_pos = f"(ih-ih/zoom)*{progress}" if normalized in {"pan_down", "scroll_down"} else f"(ih-ih/zoom)*(1-{progress})"
    else:
        zoom = "min(1.10,max(1.0,pzoom)+0.00035)"
        x_pos = "iw/2-(iw/zoom/2)"
        y_pos = "ih/2-(ih/zoom/2)"
    return (
        f"{base},zoompan=z='{zoom}':x='{x_pos}':y='{y_pos}':d=1:s={width}x{height}:fps={fps},"
        f"trim=duration={duration:.3f},setsar=1,format=yuv420p[{output_label}]"
    )


def _resolve_audio_asset(temp_dir, value):
    raw = str(value or "").strip()
    if not raw:
        return None
    candidates = [
        raw,
        os.path.join(temp_dir, raw),
        os.path.join(temp_dir, "audio", os.path.basename(raw)),
        os.path.join(temp_dir, "sfx", os.path.basename(raw)),
    ]
    return next((path for path in candidates if os.path.isfile(path)), None)


def _run_command(command, log_path, duration, progress_callback, timeout):
    started = time.monotonic()
    last_progress = 49
    with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=log_file,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            for raw_line in process.stdout or []:
                if time.monotonic() - started > timeout:
                    process.kill()
                    raise FastRenderTimeout(f"FFmpeg 빠른 렌더 제한 시간 초과 ({int(timeout)}초)")
                line = raw_line.strip()
                if not line.startswith("out_time_"):
                    continue
                key, _, raw_value = line.partition("=")
                try:
                    if key == "out_time_us":
                        rendered_seconds = int(raw_value) / 1_000_000.0
                    elif key == "out_time_ms":
                        rendered_seconds = int(raw_value) / 1_000_000.0
                    else:
                        continue
                except ValueError:
                    continue
                progress = max(50, min(89, 50 + int(39 * rendered_seconds / max(duration, 0.1))))
                if progress > last_progress:
                    progress_callback(progress, f"FFmpeg 고속 렌더링 중... {rendered_seconds:.0f}/{duration:.0f}초")
                    last_progress = progress
            return_code = process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
    if return_code != 0:
        detail = Path(log_path).read_text(encoding="utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"FFmpeg 고속 렌더 실패 (code={return_code}): {detail}")


def _is_nvenc_failure(log_path):
    detail = Path(log_path).read_text(encoding="utf-8", errors="replace").lower()
    markers = (
        "cannot load nvcuda",
        "no capable devices found",
        "openencodesessionex failed",
        "initializeencoder failed",
        "provided device doesn't support required nvenc features",
    )
    return any(marker in detail for marker in markers) or (
        "h264_nvenc" in detail and "error while opening encoder" in detail
    )


def render_ffmpeg_slideshow(
    *,
    temp_dir,
    images,
    audio_path,
    durations,
    subtitles,
    subtitle_settings,
    image_effects,
    transition_effects,
    resolution,
    template_overlay_path=None,
    intro_video_path=None,
    sfx_cues=None,
    use_gpu=False,
    progress_callback=None,
):
    if intro_video_path and os.path.exists(intro_video_path):
        raise FastRenderUnsupported("인트로 영상은 아직 고속 렌더 경로에서 지원하지 않습니다.")
    if not images or len(images) != len(durations):
        raise FastRenderUnsupported("씬 파일과 재생 시간 구성이 일치하지 않습니다.")

    progress_callback = progress_callback or (lambda _percent, _message: None)
    ffmpeg_exe = _ffmpeg_executable()
    width, height = int(resolution[0]), int(resolution[1])
    fps = 24
    audio_duration = sum(float(value) for value in durations)
    output_path = os.path.join(temp_dir, "output.mp4")
    ass_path = os.path.join(temp_dir, "subtitles.fast.ass")
    graph_path = os.path.join(temp_dir, "ffmpeg.fast.filter.txt")
    log_path = os.path.join(temp_dir, "ffmpeg.fast.log")

    command = [ffmpeg_exe, "-hide_banner", "-y"]
    filters = []
    transition_durations = []
    for index in range(len(images)):
        transition = 0.001 if index == len(images) - 1 else 0.5
        transition_durations.append(transition)

    for index, (source_path, base_duration) in enumerate(zip(images, durations)):
        if not source_path or not os.path.isfile(source_path):
            raise FastRenderUnsupported(f"씬 {index + 1} 파일이 없습니다.")
        segment_duration = float(base_duration) + transition_durations[index]
        extension = os.path.splitext(source_path)[1].lower()
        if extension in VIDEO_EXTENSIONS:
            source_duration = _media_duration(ffmpeg_exe, source_path)
            stretch = segment_duration / source_duration if source_duration > 0 else 0.0
            if 1.0 < stretch <= 3.0:
                command.extend(["-i", source_path])
                timing = f"setpts={stretch:.8f}*(PTS-STARTPTS),"
            else:
                command.extend(["-stream_loop", "-1", "-i", source_path])
                timing = "setpts=PTS-STARTPTS,"
            filters.append(
                f"[{index}:v]{timing}fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,zoompan=z=1:d=1:s={width}x{height}:fps={fps},"
                f"trim=duration={segment_duration:.3f},format=yuv420p[v{index}]"
            )
        else:
            command.extend(["-loop", "1", "-framerate", str(fps), "-i", source_path])
            effect = image_effects[index] if index < len(image_effects or []) else "auto_classify"
            filters.append(_image_filter(index, f"v{index}", width, height, fps, segment_duration, effect))

    current_label = "v0"
    timeline = float(durations[0])
    for index in range(1, len(images)):
        transition_value = transition_effects[index] if index < len(transition_effects or []) else ""
        transition_name = _transition_name(transition_value)
        duration = 0.001 if str(transition_value or "").strip().lower() == "none" else 0.5
        output_label = f"x{index}"
        filters.append(
            f"[{current_label}][v{index}]xfade=transition={transition_name}:duration={duration:.3f}:"
            f"offset={timeline:.3f}[{output_label}]"
        )
        current_label = output_label
        timeline += float(durations[index])

    if template_overlay_path and os.path.isfile(template_overlay_path):
        overlay_index = len(images)
        command.extend(["-loop", "1", "-framerate", str(fps), "-i", template_overlay_path])
        filters.append(
            f"[{overlay_index}:v]scale={width}:{height},trim=duration={audio_duration:.3f},"
            f"setpts=PTS-STARTPTS,format=rgba[template]"
        )
        filters.append(f"[{current_label}][template]overlay=0:0:shortest=1[templated]")
        current_label = "templated"

    if subtitles:
        _write_ass_file(ass_path, subtitles, subtitle_settings or {}, (width, height))
        fonts_dir = _prepare_fonts_dir(temp_dir, subtitle_settings or {})
        filters.append(
            f"[{current_label}]subtitles=filename='{_filter_path(ass_path)}':"
            f"fontsdir='{_filter_path(fonts_dir)}'[videoout]"
        )
        current_label = "videoout"

    audio_index = len(images) + (1 if template_overlay_path and os.path.isfile(template_overlay_path) else 0)
    command.extend(["-i", audio_path])
    audio_labels = []
    filters.append(f"[{audio_index}:a]atrim=duration={audio_duration:.3f},asetpts=PTS-STARTPTS[voice]")
    audio_labels.append("voice")

    bgm_path = _resolve_audio_asset(temp_dir, _setting(subtitle_settings or {}, "bgm_path"))
    if bgm_path:
        bgm_index = audio_index + 1
        command.extend(["-stream_loop", "-1", "-i", bgm_path])
        bgm_volume = float(_setting(subtitle_settings or {}, "bgm_volume", default=0.25) or 0.25)
        filters.append(
            f"[{bgm_index}:a]volume={max(0.0, min(1.0, bgm_volume)):.3f},"
            f"atrim=duration={audio_duration:.3f},asetpts=PTS-STARTPTS[bgm]"
        )
        audio_labels.append("bgm")

    next_audio_index = audio_index + 1 + (1 if bgm_path else 0)
    for cue_index, cue in enumerate(sfx_cues or []):
        cue_path = _resolve_audio_asset(
            temp_dir,
            cue.get("path") or cue.get("relative_path") or cue.get("filename"),
        )
        if not cue_path or cue.get("enabled") is False:
            continue
        command.extend(["-i", cue_path])
        label = f"sfx{cue_index}"
        delay_ms = max(0, int(float(cue.get("start") or cue.get("time") or 0) * 1000))
        volume_db = max(-60.0, min(12.0, float(cue.get("volume_db") or -18.0)))
        filters.append(
            f"[{next_audio_index}:a]volume={volume_db:.2f}dB,adelay={delay_ms}|{delay_ms}[{label}]"
        )
        audio_labels.append(label)
        next_audio_index += 1

    if len(audio_labels) > 1:
        inputs = "".join(f"[{label}]" for label in audio_labels)
        filters.append(f"{inputs}amix=inputs={len(audio_labels)}:duration=first:dropout_transition=0[audioout]")
        audio_label = "audioout"
    else:
        audio_label = "voice"

    Path(graph_path).write_text(";\n".join(filters), encoding="utf-8")
    encoder = "h264_nvenc" if use_gpu else "libx264"
    command.extend(["-filter_complex_script", graph_path, "-map", f"[{current_label}]", "-map", f"[{audio_label}]"])
    if encoder == "h264_nvenc":
        command.extend(["-c:v", encoder, "-preset", "p4", "-cq", "21"])
    else:
        command.extend(["-c:v", encoder, "-preset", "veryfast", "-crf", "20"])
    command.extend([
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-t", f"{audio_duration:.3f}", "-progress", "pipe:1", "-nostats", output_path,
    ])

    timeout = max(600, min(3600, int(audio_duration * 4)))
    progress_callback(50, "FFmpeg 고속 렌더링 시작...")
    try:
        _run_command(command, log_path, audio_duration, progress_callback, timeout)
    except FastRenderTimeout:
        raise
    except RuntimeError:
        if encoder != "h264_nvenc" or not _is_nvenc_failure(log_path):
            raise
        progress_callback(50, "NVENC 오류로 FFmpeg CPU 인코더 재시도 중...")
        if os.path.exists(output_path):
            os.remove(output_path)
        cpu_command = ["libx264" if value == "h264_nvenc" else value for value in command]
        cpu_command = ["veryfast" if value == "p4" else value for value in cpu_command]
        filtered = []
        skip_next = False
        for index, value in enumerate(cpu_command):
            if skip_next:
                skip_next = False
                continue
            if value == "-cq":
                filtered.extend(["-crf", "20"])
                skip_next = True
            else:
                filtered.append(value)
        _run_command(filtered, log_path, audio_duration, progress_callback, timeout)

    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        raise RuntimeError("FFmpeg 고속 렌더 결과 파일이 생성되지 않았습니다.")
    progress_callback(90, "FFmpeg 고속 렌더링 완료")
    return output_path
