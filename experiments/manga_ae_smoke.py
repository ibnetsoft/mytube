"""Render self-contained layered manga template smoke clips in real AE.

The hand-drawn placeholder art tests PSD import, template scripting and video
QA without cloud credentials or copyrighted reference frames.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw
from psd_tools import PSDImage
import imageio_ffmpeg


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "worker"))

from adobe_tools import find_aerender, find_afterfx  # noqa: E402
from ae_highlight_worker import _run_afterfx_script, _run_checked  # noqa: E402
from codex_content_runner import _manga_template_plan  # noqa: E402
from manga_ae_templates import MANGA_TEMPLATES, write_manga_jsx  # noqa: E402
from manga_layer_package import _build_psd  # noqa: E402
from manga_scene_qa import validate_render, validate_scene_plan  # noqa: E402
from manga_lip_sync import MOUTH_ROLES, prepare_lip_sync  # noqa: E402
from manga_caption_animation import PRESETS, prepare_caption_animation  # noqa: E402


SIZE = (1920, 1080)
OUT = ROOT / "output" / "manga-ae-smoke"
ROLES = {
    "dialogue_closeup": ("background", "character", *MOUTH_ROLES),
    "angled_triple_reaction": ("background", "character_left", "character_center", "character_right"),
    "body_following_qi": ("background", "character", "talisman"),
    "ink_splat_impact": ("background", "character", "talisman"),
    "wall_impact_debris": ("background", "wall_intact", "wall_broken", "character"),
    "glasses_reflection": ("background", "character", "reflection_scene"),
    "kinetic_title_reveal": ("background", "training_prop", "character"),
    "backlit_hand_reveal": ("background", "hand_foreground"),
}


def _draw_layer(role: str, template: str) -> Image.Image:
    if role == "background":
        color = (104, 151, 199, 255) if template == "backlit_hand_reveal" else (30, 26, 46, 255)
        image = Image.new("RGBA", SIZE, color)
        draw = ImageDraw.Draw(image)
        if template == "backlit_hand_reveal":
            for index in range(7):
                x, y = 120 + index * 270, 130 + (index % 3) * 215
                draw.ellipse((x, y, x + 370, y + 95), fill=(241, 219, 184, 210))
        elif template == "wall_impact_debris":
            draw.rectangle((0, 0, 1920, 1080), fill=(192, 185, 171, 255))
            for x in range(0, 1920, 165):
                draw.line((x, 0, x, 1080), fill=(100, 96, 91, 255), width=3)
            for y in range(0, 1080, 105):
                draw.line((0, y, 1920, y), fill=(100, 96, 91, 255), width=3)
        else:
            for y in range(0, 1080, 32):
                draw.line((0, y, 1920, y - 150), fill=(90, 78, 128, 255), width=3)
        return image
    image = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if role in MOUTH_ROLES:
        draw.rounded_rectangle((826, 325, 1094, 410), radius=24,
                               fill=(225, 171, 143, 255))
        if role == "mouth_closed":
            draw.arc((885, 355, 1035, 382), 0, 180, fill=(45, 22, 31, 255), width=7)
        elif role == "mouth_half":
            draw.ellipse((900, 349, 1020, 387), fill=(77, 27, 46, 255))
        else:
            draw.ellipse((890, 337, 1030, 400), fill=(70, 22, 40, 255))
        return image
    if role == "wall_intact":
        draw.rectangle((570, 110, 1540, 970), fill=(194, 189, 173, 255),
                       outline=(41, 40, 41, 255), width=13)
        for y in range(240, 970, 135):
            draw.line((570, y, 1540, y), fill=(105, 101, 93, 255), width=6)
        return image
    if role == "wall_broken":
        draw.rectangle((570, 110, 1540, 970), fill=(194, 189, 173, 255),
                       outline=(41, 40, 41, 255), width=13)
        draw.polygon([(820, 235), (1070, 160), (1300, 310), (1420, 510),
                      (1210, 780), (910, 860), (670, 610)],
                     fill=(54, 46, 50, 255), outline=(20, 18, 24, 255), width=18)
        for end in ((570, 235), (1400, 120), (1530, 510), (1520, 870), (690, 950), (570, 590)):
            draw.line((1040, 520, *end), fill=(24, 22, 25, 255), width=13)
        return image
    if role == "reflection_scene":
        draw.ellipse((740, 320, 1180, 820), fill=(218, 210, 190, 255),
                     outline=(47, 41, 46, 255), width=10)
        draw.arc((815, 430, 1105, 690), 15, 155, fill=(42, 34, 39, 255), width=17)
        draw.polygon([(690, 1080), (790, 780), (1130, 780), (1260, 1080)],
                     fill=(129, 100, 111, 255))
        return image
    if role == "training_prop":
        for y in range(40, 850, 95):
            draw.rounded_rectangle((845, y, 1080, y + 120), radius=25,
                                   fill=(167, 157, 144, 255), outline=(61, 55, 54, 255), width=7)
        return image
    if role == "hand_foreground":
        draw.polygon([(510, 1080), (700, 830), (600, 600), (380, 510), (340, 440),
                      (380, 405), (720, 535), (650, 215), (680, 150), (735, 175),
                      (800, 490), (880, 120), (930, 85), (985, 130), (960, 490),
                      (1135, 205), (1190, 190), (1220, 255), (1050, 570),
                      (1345, 400), (1420, 430), (1440, 500), (1110, 730),
                      (1010, 1080)],
                     fill=(64, 45, 46, 255), outline=(237, 204, 148, 255), width=13)
        return image
    if role == "talisman":
        draw.rounded_rectangle((910, 550, 1020, 755), radius=12, fill=(245, 182, 38, 255),
                               outline=(94, 31, 15, 255), width=8)
        draw.line((937, 600, 991, 701), fill=(130, 24, 20, 255), width=13)
        return image
    center = {"character_left": 345, "character_center": 960, "character_right": 1560,
              "character": 960}[role]
    color = {"character_left": (109, 160, 199, 255),
             "character_center": (90, 55, 105, 255),
             "character_right": (178, 126, 48, 255),
             "character": (113, 58, 106, 255)}[role]
    draw.polygon([(center - 280, 1040), (center - 220, 455), (center + 220, 455),
                  (center + 300, 1040)], fill=color, outline=(12, 9, 20, 255), width=9)
    draw.ellipse((center - 155, 165, center + 155, 540), fill=(225, 171, 143, 255),
                 outline=(15, 9, 18, 255), width=10)
    draw.pieslice((center - 165, 145, center + 165, 430), 180, 355,
                  fill=(19, 17, 36, 255), outline=(15, 9, 18, 255), width=7)
    draw.arc((center - 75, 305, center + 90, 365), 0, 180, fill=(25, 15, 26, 255), width=8)
    if template == "glasses_reflection":
        draw.ellipse((560, 245, 905, 580), outline=(14, 15, 25, 255), width=28)
        draw.ellipse((1015, 245, 1360, 580), outline=(14, 15, 25, 255), width=28)
        draw.line((895, 350, 1025, 350), fill=(14, 15, 25, 255), width=26)
    return image


def render_template(template: str, folder: Path, *, force: bool = False,
                    title_style: str = "training_emphasis",
                    caption_preset: str | None = None) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    layers = []
    roles = (("background", "character") if template == "kinetic_title_reveal"
             and title_style == "threat_red" else ROLES[template])
    for role in roles:
        name = f"scene-001-{role.replace('_', '-')}.png"
        _draw_layer(role, template).save(folder / name)
        layers.append({"role": role, "file": name})
    psd_path = folder / "scene.psd"
    _build_psd(folder, layers, psd_path, folder / "preview.png")
    scene_seed = {"duration_seconds": 4}
    if template == "kinetic_title_reveal":
        title = ({"text": "그들로부터 살아남을 수 있어야 한다",
                  "accent_text": "살아남을 수 있어야 한다", "style": "threat_red",
                  "position": [0.5, 0.73]}
                 if title_style == "threat_red" else
                 {"text": "말도 안 되는 근력 훈련이었죠", "accent_text": "근력 훈련",
                  "style": "training_emphasis", "position": [0.5, 0.55]})
        scene_seed["ae_template_parameters"] = {
            "title": title}
    plan = _manga_template_plan(template, scene_seed, 4)
    scene = {"duration_seconds": 4, "ae_effect_plan": {"enabled": True, **plan}}
    if template == "dialogue_closeup":
        voice = folder / "synthetic-dialogue-timing.wav"
        if not voice.is_file():
            samples = bytearray()
            for index in range(4 * 24000):
                seconds = index / 24000
                speaking = .8 <= seconds < 1.4 or 2 <= seconds < 2.5
                level = int(3500 * math.sin(seconds * 2 * math.pi * 220)) if speaking else 0
                samples.extend(level.to_bytes(2, "little", signed=True))
            with wave.open(str(voice), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(samples)
        scene["ae_effect_plan"]["character_role_keys"] = {"character": "smoke-speaker"}
        spoken_words = [
            {"text": "테스트", "start_seconds": .8, "end_seconds": 1.4,
             "speaker_key": "smoke-speaker"},
            {"text": "대사", "start_seconds": 2, "end_seconds": 2.5,
             "speaker_key": "smoke-speaker"},
        ]
        scene["ae_effect_plan"]["lip_sync"] = prepare_lip_sync(
            audio_path=voice, speaker_key="smoke-speaker", duration=4,
            mouth_box=[.43, .30, .57, .38], words=spoken_words,
        )
        if caption_preset:
            scene["ae_effect_plan"]["caption_animation"] = prepare_caption_animation(
                audio_path=voice, words=spoken_words, duration=4,
                captions=[{"preset": caption_preset, "text": "테스트 대사",
                           "accent_text": "대사", "position": [.50, .78]}],
            )
        scene["ae_effect_plan"]["asset_requirements"]["required_layers"].extend(MOUTH_ROLES)
    asset = {"local_path": str(psd_path), "layers": [layer["role"] for layer in layers],
             "qa_status": "approved"}
    plan_report = validate_scene_plan(scene, asset, 4)
    if not plan_report["passed"]:
        raise RuntimeError(f"{template} plan QA failed: {plan_report['errors']}")
    project = folder / "scene.aep"
    video = folder / "scene.mp4"
    jsx = folder / "scene.jsx"
    if force:
        project.unlink(missing_ok=True)
        video.unlink(missing_ok=True)
    imported_psd = PSDImage.open(psd_path)
    layer_centers = {}
    for layer in imported_psd:
        bounds = layer.topil().convert("RGBA").getchannel("A").getbbox()
        if bounds:
            layer_centers[str(layer.name).lower()] = [
                round((bounds[0] + bounds[2]) / (2 * SIZE[0]), 6),
                round((bounds[1] + bounds[3]) / (2 * SIZE[1]), 6),
            ]
    comp = f"ae_highlight_{template}"
    write_manga_jsx(scene=scene, input_psd=psd_path, project_path=project,
                    render_path=video, jsx_path=jsx, comp_name=comp,
                    width=1920, height=1080, fps=24, duration=4,
                    layer_centers=layer_centers)
    if not project.is_file() or not video.is_file():
        afterfx, aerender = find_afterfx(), find_aerender()
        if not afterfx or not aerender:
            raise RuntimeError("After Effects 2026 and aerender are required for the smoke")
        if not project.is_file():
            _run_afterfx_script(afterfx, jsx, project, timeout=240)
        if not video.is_file():
            _run_checked([str(aerender), "-project", str(project), "-comp", comp,
                          "-output", str(video)], timeout=1200)
    render_report = validate_render(scene, video, fps=24, duration_seconds=4)
    preview = None
    if template == "dialogue_closeup":
        preview = folder / "scene-with-audio.mp4"
        if force:
            preview.unlink(missing_ok=True)
        if not preview.is_file():
            subprocess.run([
                imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                "-i", str(video), "-i", str(folder / "synthetic-dialogue-timing.wav"),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                "-shortest", "-movflags", "+faststart", str(preview),
            ], check=True, timeout=120)
    report = {"template": template, "plan": plan_report, "render": render_report,
              "psd": str(psd_path), "aep": str(project), "mp4": str(video),
              "audio_preview": str(preview) if preview else None}
    (folder / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", choices=sorted(MANGA_TEMPLATES))
    parser.add_argument("--title-style", choices=("training_emphasis", "threat_red"),
                        default="training_emphasis")
    parser.add_argument("--force", action="store_true", help="Rebuild the AEP and MP4 with the current template script")
    parser.add_argument("--caption-preset", choices=sorted(PRESETS),
                        help="Render one opt-in animated-caption smoke on dialogue_closeup")
    args = parser.parse_args()
    if args.caption_preset and args.template != "dialogue_closeup":
        parser.error("--caption-preset requires --template dialogue_closeup")
    templates = [args.template] if args.template else sorted(MANGA_TEMPLATES)
    for template in templates:
        folder = OUT / (template + "_caption_" + args.caption_preset if args.caption_preset else
                        template + "_threat_red" if template == "kinetic_title_reveal"
                        and args.title_style == "threat_red" else template)
        report = render_template(template, folder, force=args.force,
                                 title_style=args.title_style, caption_preset=args.caption_preset)
        print(json.dumps({"template": template, "plan_passed": report["plan"]["passed"],
                          "render_passed": report["render"]["passed"], "mp4": report["mp4"]},
                         ensure_ascii=False), flush=True)
        if not report["render"]["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
