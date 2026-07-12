"""
[AIR-0227B Stage 12] Local E2E fixture builder.

Generates a minimal, self-contained render_video input package (no network,
no Google Drive, no real project) in worker/fixture/sample_render/, matching
exactly the config.json schema services/remote_render_service.py::
remote_render_executor_func expects (Stage 1 re-verification). Running this
script standalone regenerates the fixture; render_worker.py consumes it
through render_pipeline_adapter.prepare_temp_dir() the same way it would
consume a real downloaded asset package.
"""
import json
import subprocess
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "sample_render"
IMAGES_DIR = FIXTURE_DIR / "images"
AUDIO_DIR = FIXTURE_DIR / "audio"

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def _run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg command failed: {' '.join(cmd)}\n{result.stderr}")


def build():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Two small distinct color-pattern stills (16:9, 1280x720) - enough to
    # prove create_slideshow() actually composites multiple scenes.
    _run([FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=1:duration=1",
          "-frames:v", "1", str(IMAGES_DIR / "scene1.jpg")])
    _run([FFMPEG, "-y", "-f", "lavfi", "-i", "smptebars=size=1280x720:rate=1:duration=1",
          "-frames:v", "1", str(IMAGES_DIR / "scene2.jpg")])

    # 4-second silent mono voice track.
    _run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "4",
          "-q:a", "9", str(AUDIO_DIR / "voice.mp3")])

    config = {
        "project_id": None,
        "project_name": "AIR-0227B Local E2E Fixture",
        "app_mode": "longform",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "audio_filename": "voice.mp3",
        "audio_duration": 4.0,
        "images": ["scene1.jpg", "scene2.jpg"],
        "subtitles": [],
        "use_subtitles": False,
        "render_settings": {},
        "image_timing_starts": [0.0, 2.0],
        "image_effects": [],
        "focal_point_ys": [],
    }
    (FIXTURE_DIR / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fixture built at {FIXTURE_DIR}")
    return FIXTURE_DIR


if __name__ == "__main__":
    build()
