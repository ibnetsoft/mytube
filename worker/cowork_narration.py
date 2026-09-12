"""Local audio stage for the browser-capable Codex/CoWork worker.

Browser actions are performed by the connected Codex browser tool; this module
owns ordered segments, validated file imports, dialogue TTS, and assembly.
It does not pretend a plain `codex exec` subprocess inherits desktop browsers.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]


def ffmpeg_path() -> str:
    configured = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
    if configured:
        return configured
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    for base in (Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "AIRWorker/_internal",
                 Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "AIRStudio/app/_internal"):
        candidates = sorted(base.glob("imageio_ffmpeg/binaries/ffmpeg*.exe"))
        if candidates:
            return str(candidates[0])
    raise RuntimeError("Worker FFmpeg is unavailable")


def save_manifest(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def prepare(segments: list[dict], directory: Path) -> Path:
    if not segments:
        raise ValueError("No segments supplied")
    entries = []
    for index, segment in enumerate(segments, 1):
        kind = segment.get("kind")
        text = str(segment.get("text") or "").strip()
        if kind not in {"narration", "dialogue"} or not text:
            raise ValueError(f"Segment {index}: explicit kind and text required")
        if kind == "dialogue" and not segment.get("voice_id"):
            raise ValueError(f"Segment {index}: dialogue voice_id required; speaker is never guessed")
        if kind == "narration" and len(text) > 2000:
            raise ValueError(f"Segment {index}: split narration at sentence boundaries below 2000 characters")
        entries.append({"id": f"segment-{index:04d}", "kind": kind, "text": text,
                        "voice_id": segment.get("voice_id"), "state": "pending"})
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "narration.json"
    save_manifest(path, {"schema": "air-cowork-narration/v1", "job_id": str(uuid.uuid4()),
                         "status": "pending", "segments": entries})
    return path


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "air-cowork-narration/v1":
        raise ValueError("Unsupported narration manifest")
    return data


def wave_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as audio:
        frames = audio.getnframes()
        rate = audio.getframerate()
        if not frames or rate != 48000 or audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError("Expected nonempty 48 kHz mono PCM16 WAV")
        return {"frames": frames, "sample_rate": rate, "duration_seconds": frames / rate}


def accept(path: Path, segment_id: str, source: Path) -> dict:
    """Copy/decode a file selected by the browser worker, never by 'latest file'."""
    data = load_manifest(path)
    segment = next((s for s in data["segments"] if s["id"] == segment_id), None)
    if segment is None:
        raise ValueError("Unknown segment")
    if segment["state"] == "ready":
        raise ValueError("Segment already ready; do not overwrite verified audio")
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("Missing or empty source audio")
    before = source.stat()
    target = path.parent / f"{segment_id}.wav"
    temporary = path.parent / f"{segment_id}.part.wav"
    completed = subprocess.run([ffmpeg_path(), "-nostdin", "-v", "error", "-xerror", "-y", "-i", str(source.resolve()),
                                "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(temporary.resolve())],
                               capture_output=True, timeout=180, check=False)
    try:
        if completed.returncode:
            raise ValueError("Audio decode failed: " + completed.stderr.decode(errors="replace")[-500:])
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Source file is still changing")
        info = wave_info(temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    segment.update(state="ready", file=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(), **info)
    save_manifest(path, data)
    return segment


async def generate_dialogue(path: Path) -> None:
    # Narration is deliberately never routed to a paid fallback.
    import sys
    sys.path.insert(0, str(ROOT))
    from services.tts_service import tts_service
    for segment in load_manifest(path)["segments"]:
        if segment["kind"] != "dialogue" or segment["state"] == "ready":
            continue
        source = (path.parent / f"{segment['id']}-elevenlabs.mp3").resolve()
        result = await tts_service.generate_elevenlabs(segment["text"], segment["voice_id"], str(source), return_alignment=True)
        if not isinstance(result, dict) or not result.get("audio_path"):
            raise RuntimeError("ElevenLabs did not return audio")
        accept(path, segment["id"], Path(result["audio_path"]))


def assemble(path: Path) -> dict:
    data = load_manifest(path)
    if any(s["state"] != "ready" for s in data["segments"]):
        raise ValueError("Every narration and dialogue segment must be ready before assembly")
    # Validate all inputs before creating the combined output.
    for segment in data["segments"]:
        source = (path.parent / segment["file"]).resolve()
        if source.parent != path.parent.resolve():
            raise ValueError("Segment path escaped job directory")
        if hashlib.sha256(source.read_bytes()).hexdigest() != segment["sha256"]:
            raise ValueError("Segment audio changed after validation")
        wave_info(source)
    frames = 0
    timeline = []
    temporary = path.parent / "narration-mixed.part.wav"
    final = path.parent / "narration-mixed.wav"
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            for segment in data["segments"]:
                start = frames
                with wave.open(str(path.parent / segment["file"]), "rb") as audio:
                    while chunk := audio.readframes(48000):
                        output.writeframesraw(chunk)
                        frames += len(chunk) // 2
                timeline.append({"id": segment["id"], "kind": segment["kind"], "text": segment["text"],
                                 "start": start / 48000, "end": frames / 48000})
        temporary.replace(final)
    finally:
        temporary.unlink(missing_ok=True)
    data.update(status="assembled", output=final.name, timeline=timeline, duration_seconds=frames / 48000)
    save_manifest(path, data)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("prepare")
    command.add_argument("--segments", type=Path, required=True)
    command.add_argument("--directory", type=Path, required=True)
    for action in ("accept", "dialogue", "assemble", "status"):
        command = sub.add_parser(action)
        command.add_argument("--manifest", type=Path, required=True)
        if action == "accept":
            command.add_argument("--segment", required=True)
            command.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        print(prepare(json.loads(args.segments.read_text(encoding="utf-8-sig")), args.directory))
    elif args.action == "accept":
        print(json.dumps(accept(args.manifest, args.segment, args.source), ensure_ascii=False))
    elif args.action == "dialogue":
        asyncio.run(generate_dialogue(args.manifest))
    elif args.action == "assemble":
        print(json.dumps(assemble(args.manifest), ensure_ascii=False))
    else:
        print(json.dumps(load_manifest(args.manifest), ensure_ascii=False))


if __name__ == "__main__":
    main()
