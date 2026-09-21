import os
import json
import re
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path
from services.subtitle_layout import subtitle_font_pixels


class FastRenderUnsupported(RuntimeError):
    pass


class FastRenderTimeout(RuntimeError):
    pass


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _web_font_catalog():
    root = Path(__file__).resolve().parents[1] / 'auth-web' / 'public' / 'fonts'
    return root, json.loads((root / 'catalog.json').read_text(encoding='utf-8'))


def _ass_font_family(font_name):
    return {
        'ChosunIlboMyungjo': 'Chosunilbo_myungjo',
        'Chosun_ilbo_myungjottf': 'Chosunilbo_myungjo',
        'GmarketSans': 'GmarketSansBold',
        'NotoSansJP': 'Noto Sans CJK JP',
    }.get(font_name, font_name)


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
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", f"{result.stdout or ''}\n{result.stderr or ''}")
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


def _bool_setting(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _float_setting(settings, keys, default):
    value = _setting(settings, *keys, default=None)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except Exception:
        return default


def _opacity_setting(settings, keys, default):
    value = _float_setting(settings, keys, default)
    if value > 1.0:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def _rounded_ass_path(width, height, radius):
    """A single filled contour: translucent corners must not overlap."""
    r = min(radius, width / 2, height / 2)
    c = r * 0.5522847498
    def point(x, y):
        return f"{x:.3f} {y:.3f}"
    return " ".join([
        "m", point(r, 0), "l", point(width-r, 0),
        "b", point(width-r+c, 0), point(width, r-c), point(width, r),
        "l", point(width, height-r),
        "b", point(width, height-r+c), point(width-r+c, height), point(width-r, height),
        "l", point(r, height),
        "b", point(r-c, height), point(0, height-r+c), point(0, height-r),
        "l", point(0, r),
        "b", point(0, r-c), point(r-c, 0), point(r, 0),
    ])


def _subtitle_layout_font(fonts_dir, font_name, font_size):
    from PIL import ImageFont

    loaded = []
    for candidate in sorted(Path(fonts_dir).glob("*")):
        if candidate.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            continue
        try:
            font = ImageFont.truetype(str(candidate), font_size)
        except OSError:
            continue
        loaded.append(font)
        if font.getname()[0].casefold() == font_name.casefold():
            return font
    if len(loaded) == 1 and Path(fonts_dir).name == "fast_render_fonts":
        return loaded[0]
    # Do not silently measure with an unrelated font: the compatibility renderer
    # can resolve fonts that the fast renderer cannot use for exact box layout.
    raise FastRenderUnsupported(f"자막 배경 측정용 폰트를 찾을 수 없습니다: {font_name}")


def _wrap_ass_lines(text, font, max_width):
    lines = []
    for paragraph in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = ""
        for char in paragraph:
            if line and font.getlength(line + char) > max_width:
                # Prefer word boundaries, but allow CJK/unbroken text to wrap.
                split = line.rfind(" ")
                if split > 0:
                    lines.append(line[:split])
                    line = line[split+1:] + char
                else:
                    lines.append(line)
                    line = char
            else:
                line += char
        lines.append(line)
    return lines


def _write_ass_file(path, subtitles, settings, resolution, fonts_dir=None):
    width, height = resolution
    font_name = str(_setting(
        settings,
        "subtitle_font_family",
        "fontFamily",
        "subtitle_font",
        "font",
        default="Malgun Gothic",
    ))
    font_name = _ass_font_family(font_name)

    font_value = _float_setting(settings, ("subtitle_font_size", "fontSize", "font_size"), 5.0)
    font_size = round(subtitle_font_pixels(font_value, width), 3)
    font_size = max(12, font_size)
    primary = _ass_color(_setting(
        settings,
        "subtitle_text_color",
        "textColor",
        "subtitle_base_color",
        "font_color",
        default="#ffffff",
    ))
    outline = _ass_color(_setting(settings, "subtitle_stroke_color", "strokeColor", "stroke_color", default="#000000"))
    outline_width = _float_setting(settings, ("subtitle_stroke_width", "strokeWidth", "stroke_width"), 2.0)

    bg_enabled = _bool_setting(_setting(settings, "subtitle_bg_enabled", "bgEnabled", "bg_enabled", default=0), False)
    bg_opacity = _opacity_setting(settings, ("subtitle_bg_opacity", "bgOpacity", "bg_opacity"), 0.5)
    back_alpha = int((1.0 - bg_opacity) * 255) if bg_enabled else 255
    back = _ass_color(_setting(settings, "subtitle_bg_color", "bgColor", "bg_color", default="#000000"), back_alpha)
    border_style = 1

    raw_position = str(_setting(settings, "subtitle_pos_y", "posY", "pos_y", default="b:12%") or "b:12%")
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
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary},{primary},{outline},{back},0,0,0,0,100,100,0,0,{border_style},{outline_width:.2f},0,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    layout_font = None
    if bg_enabled:
        fonts_dir = fonts_dir or _prepare_fonts_dir(Path(path).parent, settings)
        layout_font = _subtitle_layout_font(fonts_dir, font_name, font_size)
    events = []
    for subtitle in subtitles or []:
        start = float(subtitle.get("start") or 0.0)
        end = float(subtitle.get("end") or start)
        text = _ass_text(subtitle.get("text"))
        if text and end > start:
            if layout_font is not None:
                # Match the preview's em-based padding, radius and line boxes.
                pad_x, pad_y = font_size * 0.6, font_size * 0.30
                # Subtitle blocks are authored as single lines in the editor.
                # Preserve explicit breaks only; libass must not reflow them.
                lines = str(subtitle.get("text") or '').splitlines() or ['']
                box_width = max(layout_font.getlength(line) for line in lines) + 2 * pad_x
                spacing = _float_setting(settings, ("subtitle_line_spacing", "lineSpacing", "line_spacing_ratio", "line_spacing"), 0.1)
                line_height = font_size * max(0.5, 1 + spacing)
                box_height = font_size + (len(lines)-1) * line_height + 2 * pad_y
                offset = _float_setting(settings, ("subtitle_bg_v_offset", "bgVOffset", "bg_v_offset"), 0)
                left = (width - box_width) / 2
                top = height - margin_v - box_height + offset
                shape = _rounded_ass_path(box_width, box_height, font_size * 0.25)
                tags = (rf"{{\an7\pos({left:.3f},{top:.3f})\bord0\shad0"
                        rf"\1c{back}\1a&H{back_alpha:02X}&\p1}}")
                events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{tags}{shape}{{\\p0}}")
                for index, line in enumerate(lines):
                    y = top - offset + pad_y + index * line_height + font_size / 2
                    tags = rf"{{\an5\pos({width/2:.3f},{y:.3f})\q2}}"
                    events.append(f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{tags}{_ass_text(line)}")
                continue
            events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}")
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")


def _prepare_fonts_dir(temp_dir, settings):
    font_name = str(_setting(
        settings,
        "subtitle_font_family",
        "fontFamily",
        "subtitle_font",
        "font",
        default="Malgun Gothic",
    ))
    web_root, catalog = _web_font_catalog()
    web_name = {'GmarketSans': 'GmarketSansBold', 'Chosunilbo_myungjo': 'ChosunIlboMyungjo',
                'Chosun_ilbo_myungjottf': 'ChosunIlboMyungjo'}.get(font_name, font_name)
    if web_name in catalog:
        source = web_root / catalog[web_name]
        if not source.is_file():
            raise FastRenderUnsupported(f'선택한 웹 폰트 파일이 없습니다: {web_name}')
        destination_dir = Path(temp_dir) / 'fast_render_fonts'
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / (source.stem + '.ttf')
        if source.suffix == '.woff':
            _convert_woff_to_ttf(source, destination)
        else:
            shutil.copy2(source, destination)
        _rewrite_sfnt_family_name(destination, _ass_font_family(web_name))
        return str(destination_dir)
    aliases = {
        "Malgun Gothic": ["malgun.ttf"],
        "GmarketSans": ["GmarketSansTTFBold.ttf", "GmarketSansBold.woff"],
        "GmarketSansBold": ["GmarketSansTTFBold.ttf", "GmarketSansBold.woff"],
        "ChosunIlboMyungjo": ["ChosunIlboMyungjo.ttf", "Chosunilbo_myungjo.woff"],
        "Chosunilbo_myungjo": ["ChosunIlboMyungjo.ttf", "Chosunilbo_myungjo.woff"],
        "Chosun_ilbo_myungjottf": ["ChosunIlboMyungjo.ttf", "Chosunilbo_myungjo.woff"],
        "NotoSansJP": ["NotoSansJP-Bold.ttf", "NotoSansJP-Regular.ttf"],
        "CookieRun-Regular": ["CookieRun-Regular.woff"],
    }
    family_overrides = {
        "BinggraeMelona-Bold": "BinggraeMelona-Bold",
        "ChosunIlboMyungjo": "Chosunilbo_myungjo",
        "Chosun_ilbo_myungjottf": "Chosunilbo_myungjo",
        "Chosunilbo_myungjo": "Chosunilbo_myungjo",
        "GmarketSans": "GmarketSansBold",
        "GmarketSansBold": "GmarketSansBold",
        "Jalnan": "Jalnan",
        "MapoFlowerIsland": "MapoFlowerIsland",
    }
    candidates = aliases.get(font_name, [font_name, f"{font_name}.ttf", f"{font_name}.otf", f"{font_name}.woff"])
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
        f"[{input_index}:v]scale={int(width * 1.08)}:{int(height * 1.08)}:"
        f"force_original_aspect_ratio=increase,crop={int(width * 1.08)}:{int(height * 1.08)}"
    )
    frames = max(1, int(duration * fps) - 1)
    progress = f"(1-cos(PI*min(1,on/{frames})))/2"
    if normalized in {"none", "static"}:
        return (
            f"{base},scale={width}:{height},fps={fps},trim=duration={duration:.3f},"
            f"setsar=1,format=yuv420p[{output_label}]"
        )
    if normalized not in {"pan_left", "pan_right", "pan_up", "scroll_up", "pan_down", "scroll_down"}:
        # zoompan truncates its crop rectangle to whole pixels (and chroma
        # boundaries), which makes slow zooms visibly wobble. Perspective's
        # cubic sampler keeps the centre and crop corners at subpixel precision.
        zoom = f"1+0.04*(1-{progress})" if normalized == "zoom_out" else f"1+0.04*{progress}"
        x0, y0 = f"W/2-W/(2*({zoom}))", f"H/2-H/(2*({zoom}))"
        x1, y1 = f"W/2+W/(2*({zoom}))", f"H/2+H/(2*({zoom}))"
        return (
            f"{base},scale={width}:{height}:flags=lanczos,fps={fps},format=yuv444p,"
            f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':"
            f"x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}':"
            f"sense=source:eval=frame:interpolation=cubic,"
            f"trim=duration={duration:.3f},setsar=1,format=yuv420p[{output_label}]"
        )
    if normalized in {"pan_left", "pan_right"}:
        zoom = "1.12"
        x_pos = f"trunc((iw-iw/zoom)*{progress})" if normalized == "pan_left" else f"trunc((iw-iw/zoom)*(1-{progress}))"
        y_pos = "trunc(ih/2-(ih/zoom/2))"
    else:
        zoom = "1.12"
        x_pos = "trunc(iw/2-(iw/zoom/2))"
        y_pos = f"trunc((ih-ih/zoom)*{progress})" if normalized in {"pan_up", "scroll_up"} else f"trunc((ih-ih/zoom)*(1-{progress}))"
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
    visual_duration = sum(float(value) for value in durations)
    probed_audio_duration = _media_duration(ffmpeg_exe, audio_path)
    audio_duration = max(probed_audio_duration, visual_duration)
    if durations and abs(visual_duration - audio_duration) > 0.25:
        durations = list(durations)
        durations[-1] = max(0.1, float(durations[-1]) + (audio_duration - visual_duration))
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
        fonts_dir = _prepare_fonts_dir(temp_dir, subtitle_settings or {})
        _write_ass_file(ass_path, subtitles, subtitle_settings or {}, (width, height), fonts_dir)
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
        if _setting(subtitle_settings or {}, "bgm_loop", default=True):
            command.extend(["-stream_loop", "-1"])
        command.extend(["-i", bgm_path])
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
        trim = f"atrim=duration={max(.2, min(30., float(cue['duration']))):.3f}," if cue.get("duration") else ""
        filters.append(
            f"[{next_audio_index}:a]{trim}volume={volume_db:.2f}dB,adelay={delay_ms}|{delay_ms}[{label}]"
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
