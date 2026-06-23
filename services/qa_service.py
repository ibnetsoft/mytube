"""Pre-upload video QA pipeline.

Stage 1 runs local FFmpeg/FFprobe checks and optional LUFS normalization.
Stage 2 runs a lightweight Gemini semantic pass when enabled.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import database as db
from config import config


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _bool_setting(settings: Dict[str, Any], key: str, default: bool) -> bool:
    value = settings.get(key)
    if value is None:
        value = db.get_global_setting(key, default, value_type="bool")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float_setting(settings: Dict[str, Any], key: str, default: float) -> float:
    value = settings.get(key)
    if value is None:
        value = db.get_global_setting(key, str(default))
    try:
        return float(value)
    except Exception:
        return default


def _int_setting(settings: Dict[str, Any], key: str, default: int) -> int:
    value = settings.get(key)
    if value is None:
        value = db.get_global_setting(key, str(default))
    try:
        return int(float(value))
    except Exception:
        return default


def get_qa_settings() -> Dict[str, Any]:
    return {
        "qa_enable_pipeline": db.get_global_setting("qa_enable_pipeline", True, value_type="bool"),
        "qa_enable_technical_check": db.get_global_setting("qa_enable_technical_check", True, value_type="bool"),
        "qa_enable_semantic_check": db.get_global_setting("qa_enable_semantic_check", False, value_type="bool"),
        "qa_auto_normalize_lufs": db.get_global_setting("qa_auto_normalize_lufs", True, value_type="bool"),
        "qa_hold_on_technical_fail": db.get_global_setting("qa_hold_on_technical_fail", True, value_type="bool"),
        "qa_hold_on_semantic_fail": db.get_global_setting("qa_hold_on_semantic_fail", True, value_type="bool"),
        "qa_target_lufs": _float_setting({}, "qa_target_lufs", -14.0),
        "qa_lufs_tolerance": _float_setting({}, "qa_lufs_tolerance", 2.0),
        "qa_blackdetect_min_duration": _float_setting({}, "qa_blackdetect_min_duration", 1.0),
        "qa_min_width": _int_setting({}, "qa_min_width", 1920),
        "qa_min_height": _int_setting({}, "qa_min_height", 1080),
    }


def _ffmpeg_path() -> str:
    return getattr(config, "FFMPEG_PATH", None) or shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe_path() -> str:
    ffmpeg = _ffmpeg_path()
    ffmpeg_dir = os.path.dirname(ffmpeg) if ffmpeg else ""
    candidates = []
    if ffmpeg_dir:
        candidates.extend([
            os.path.join(ffmpeg_dir, "ffprobe.exe"),
            os.path.join(ffmpeg_dir, "ffprobe"),
        ])
    which = shutil.which("ffprobe")
    if which:
        candidates.append(which)
    candidates.append("ffprobe")
    return next((p for p in candidates if p == "ffprobe" or os.path.exists(p)), "ffprobe")


def _run_command(cmd: List[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _to_abs_video_path(video_path: str) -> str:
    if not video_path:
        return video_path
    if os.path.isabs(video_path):
        return video_path
    normalized = video_path.replace("\\", "/")
    if normalized.startswith("/output/"):
        return os.path.join(config.OUTPUT_DIR, normalized.replace("/output/", "", 1))
    if normalized.startswith("output/"):
        return os.path.join(config.OUTPUT_DIR, normalized.replace("output/", "", 1))
    if normalized.startswith("external/"):
        return os.path.join(config.LOCAL_APP_DATA_DIR, normalized.replace("external/", "", 1))
    return os.path.abspath(video_path)


def _to_web_video_path(abs_path: str) -> str:
    try:
        rel = os.path.relpath(abs_path, config.OUTPUT_DIR).replace("\\", "/")
        if not rel.startswith(".."):
            return f"/output/{rel}"
    except Exception:
        pass
    return abs_path


def _parse_fps(raw: str) -> float:
    if not raw or raw == "0/0":
        return 0.0
    if "/" in raw:
        num, den = raw.split("/", 1)
        try:
            return float(num) / float(den or 1)
        except Exception:
            return 0.0
    try:
        return float(raw)
    except Exception:
        return 0.0


def _probe_video(video_path: str) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    cmd = [
        _ffprobe_path(),
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        video_path,
    ]
    try:
        proc = _run_command(cmd, timeout=90)
        if proc.returncode != 0:
            warnings.append(f"ffprobe failed: {proc.stderr.strip()[:500]}")
            return {}, warnings
        data = json.loads(proc.stdout or "{}")
    except Exception as e:
        warnings.append(f"ffprobe error: {e}")
        return {}, warnings

    streams = data.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fmt = data.get("format") or {}

    info = {
        "duration_sec": float(fmt.get("duration") or video_stream.get("duration") or 0),
        "size_bytes": int(float(fmt.get("size") or 0)),
        "bit_rate": int(float(fmt.get("bit_rate") or 0)),
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "fps": _parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0"),
        "video_codec": video_stream.get("codec_name") or "",
        "audio_codec": audio_stream.get("codec_name") or "",
        "audio_sample_rate": int(float(audio_stream.get("sample_rate") or 0)) if audio_stream else 0,
        "has_video": bool(video_stream),
        "has_audio": bool(audio_stream),
    }
    return info, warnings


def _measure_lufs(video_path: str, target_lufs: float) -> Tuple[Optional[float], List[str]]:
    warnings: List[str] = []
    cmd = [
        _ffmpeg_path(),
        "-hide_banner",
        "-nostats",
        "-i",
        video_path,
        "-af",
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = _run_command(cmd, timeout=240)
        combined = (proc.stderr or "") + "\n" + (proc.stdout or "")
        match = re.search(r"\{\s*\"input_i\".*?\}", combined, re.DOTALL)
        if not match:
            warnings.append("LUFS 측정 결과를 파싱하지 못했습니다.")
            return None, warnings
        data = json.loads(match.group(0))
        measured = float(data.get("input_i"))
        return measured, warnings
    except Exception as e:
        warnings.append(f"LUFS 측정 실패: {e}")
        return None, warnings


def _normalize_lufs(video_path: str, target_lufs: float) -> Tuple[Optional[str], Optional[str]]:
    source = Path(video_path)
    output = source.with_name(f"{source.stem}_lufs{str(target_lufs).replace('-', 'm').replace('.', '_')}{source.suffix}")
    cmd = [
        _ffmpeg_path(),
        "-y",
        "-i",
        str(source),
        "-af",
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output),
    ]
    try:
        proc = _run_command(cmd, timeout=600)
        if proc.returncode != 0 or not output.exists():
            return None, (proc.stderr or "LUFS normalization failed")[:800]
        return str(output), None
    except Exception as e:
        return None, str(e)


def _detect_black_segments(video_path: str, min_duration: float) -> Tuple[List[Dict[str, float]], List[str]]:
    warnings: List[str] = []
    cmd = [
        _ffmpeg_path(),
        "-hide_banner",
        "-nostats",
        "-i",
        video_path,
        "-vf",
        f"blackdetect=d={min_duration}:pic_th=0.98",
        "-an",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = _run_command(cmd, timeout=240)
        combined = (proc.stderr or "") + "\n" + (proc.stdout or "")
        segments = []
        for match in re.finditer(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)\s+black_duration:([0-9.]+)", combined):
            segments.append({
                "start": float(match.group(1)),
                "end": float(match.group(2)),
                "duration": float(match.group(3)),
            })
        return segments, warnings
    except Exception as e:
        warnings.append(f"blackdetect 실패: {e}")
        return [], warnings


def _persist_result(project_id: int, result: Dict[str, Any]) -> None:
    db.update_project_setting(project_id, "qa_status", result.get("final_status", "warning"))
    db.update_project_setting(project_id, "qa_hold_upload", "1" if result.get("hold_upload") else "0")
    db.update_project_setting(project_id, "qa_checked_at", result.get("checked_at") or _now_iso())
    db.update_project_setting(project_id, "qa_result_json", json.dumps(result, ensure_ascii=False))
    normalized_path = (result.get("technical") or {}).get("loudness", {}).get("normalized_path")
    if normalized_path:
        db.update_project_setting(project_id, "qa_normalized_video_path", normalized_path)


def run_technical_qa(project_id: int, video_path: str, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = settings or get_qa_settings()
    result = {
        "status": "skipped",
        "ffprobe": {},
        "loudness": {},
        "blackdetect": {"has_black_segments": False, "segments": []},
        "warnings": [],
        "errors": [],
    }

    if not _bool_setting(settings, "qa_enable_pipeline", True) or not _bool_setting(settings, "qa_enable_technical_check", True):
        result["status"] = "skipped"
        return result

    abs_path = _to_abs_video_path(video_path)
    if not abs_path or not os.path.exists(abs_path):
        result["status"] = "failed"
        result["errors"].append(f"영상 파일을 찾을 수 없습니다: {video_path}")
        return result

    file_size = os.path.getsize(abs_path)
    if file_size <= 0:
        result["errors"].append("영상 파일 크기가 0입니다.")

    probe, probe_warnings = _probe_video(abs_path)
    result["ffprobe"] = probe
    result["warnings"].extend(probe_warnings)

    min_width = _int_setting(settings, "qa_min_width", 1920)
    min_height = _int_setting(settings, "qa_min_height", 1080)
    if not probe.get("has_video"):
        result["errors"].append("비디오 스트림이 없습니다.")
    if not probe.get("has_audio"):
        result["warnings"].append("오디오 스트림이 없습니다.")
    if probe.get("duration_sec", 0) <= 0:
        result["errors"].append("영상 길이를 확인할 수 없습니다.")
    width = probe.get("width", 0)
    height = probe.get("height", 0)
    # Longform landscape and shorts portrait are both allowed if either axis pair satisfies the target.
    if width and height and not ((width >= min_width and height >= min_height) or (width >= min_height and height >= min_width)):
        result["errors"].append(f"해상도 미달: {width}x{height} (기준 {min_width}x{min_height} 또는 세로형 허용)")
    if probe.get("fps", 0) and probe.get("fps", 0) < 23:
        result["warnings"].append(f"FPS가 낮습니다: {probe.get('fps'):.2f}")
    if probe.get("video_codec") and probe.get("video_codec") not in {"h264", "hevc", "mpeg4"}:
        result["warnings"].append(f"비디오 코덱 확인 필요: {probe.get('video_codec')}")

    target_lufs = _float_setting(settings, "qa_target_lufs", -14.0)
    tolerance = _float_setting(settings, "qa_lufs_tolerance", 2.0)
    measured_lufs, lufs_warnings = _measure_lufs(abs_path, target_lufs)
    result["warnings"].extend(lufs_warnings)
    result["loudness"] = {
        "measured_lufs": measured_lufs,
        "target_lufs": target_lufs,
        "tolerance": tolerance,
        "normalized": False,
    }
    if measured_lufs is not None and abs(measured_lufs - target_lufs) > tolerance:
        result["warnings"].append(f"LUFS 기준 이탈: {measured_lufs:.1f} LUFS (목표 {target_lufs})")
        if _bool_setting(settings, "qa_auto_normalize_lufs", True):
            normalized_path, error = _normalize_lufs(abs_path, target_lufs)
            if normalized_path:
                web_path = _to_web_video_path(normalized_path)
                result["loudness"].update({
                    "normalized": True,
                    "normalized_path": normalized_path,
                    "normalized_web_path": web_path,
                })
                db.update_project_setting(project_id, "qa_normalized_video_path", normalized_path)
                db.update_project_setting(project_id, "video_path", web_path)
            else:
                result["errors"].append(f"LUFS 자동 보정 실패: {error}")

    black_duration = _float_setting(settings, "qa_blackdetect_min_duration", 1.0)
    segments, black_warnings = _detect_black_segments(abs_path, black_duration)
    result["warnings"].extend(black_warnings)
    result["blackdetect"] = {
        "has_black_segments": bool(segments),
        "segments": segments,
        "min_duration": black_duration,
    }
    if segments:
        result["warnings"].append(f"검은 화면 구간 감지: {len(segments)}개")

    if result["errors"]:
        result["status"] = "failed"
    elif result["warnings"]:
        result["status"] = "warning"
    else:
        result["status"] = "passed"
    return result


def _extract_frames(video_path: str, count: int = 5) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    abs_path = _to_abs_video_path(video_path)
    if not abs_path or not os.path.exists(abs_path):
        return [], ["프레임 추출 대상 영상이 없습니다."]
    probe, _ = _probe_video(abs_path)
    duration = max(float(probe.get("duration_sec") or 0), 1.0)
    tmp_dir = tempfile.mkdtemp(prefix="qa_frames_")
    frames: List[str] = []
    for idx in range(count):
        ts = min(duration - 0.1, max(0.1, duration * (idx + 1) / (count + 1)))
        out = os.path.join(tmp_dir, f"frame_{idx+1}.jpg")
        cmd = [_ffmpeg_path(), "-y", "-ss", str(ts), "-i", abs_path, "-frames:v", "1", "-q:v", "3", out]
        try:
            proc = _run_command(cmd, timeout=60)
            if proc.returncode == 0 and os.path.exists(out):
                frames.append(out)
        except Exception as e:
            warnings.append(f"프레임 추출 실패({idx+1}): {e}")
    if not frames:
        warnings.append("대표 프레임을 추출하지 못했습니다.")
    return frames, warnings


async def run_semantic_qa(project_id: int, video_path: str, metadata: Optional[Dict[str, Any]] = None, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = settings or get_qa_settings()
    result = {
        "status": "skipped",
        "issues": [],
        "warnings": [],
        "summary": "",
    }
    if not _bool_setting(settings, "qa_enable_pipeline", True) or not _bool_setting(settings, "qa_enable_semantic_check", False):
        result["summary"] = "AI 정밀 검사가 비활성화되어 건너뜀"
        return result

    frames, frame_warnings = _extract_frames(video_path, count=5)
    result["warnings"].extend(frame_warnings)
    if not frames:
        result["status"] = "warning"
        result["summary"] = "대표 프레임 추출 실패로 AI 정밀 검사를 건너뜀"
        return result

    try:
        from services.gemini_service import gemini_service

        prompt = f"""
You are a YouTube pre-upload QA reviewer. Review the extracted representative video frames and metadata.
Return STRICT JSON only with this schema:
{{"status":"passed|warning|failed","summary":"short Korean summary","issues":[{{"severity":"warning|failed","category":"visual|subtitle|policy|metadata","message":"Korean issue text"}}]}}

Check for black/blank frames, severe AI visual collapse, cropped subtitles/text, mismatch with metadata, and YouTube policy risks.
Metadata:
{json.dumps(metadata or {}, ensure_ascii=False)}
"""
        # Different gemini service versions expose different vision helpers. Use the available one if present.
        if hasattr(gemini_service, "analyze_images"):
            raw = await gemini_service.analyze_images(frames, prompt=prompt, project_id=project_id)
        elif hasattr(gemini_service, "generate_vision_content"):
            raw = await gemini_service.generate_vision_content(prompt, frames, project_id=project_id)
        else:
            raw = await gemini_service.generate_text(prompt, temperature=0.2, project_id=project_id, task_type="qa")
        raw = re.sub(r"^```json\s*", "", str(raw).strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        parsed = json.loads(raw)
        status = parsed.get("status") if parsed.get("status") in {"passed", "warning", "failed"} else "warning"
        result.update({
            "status": status,
            "summary": parsed.get("summary") or "AI 정밀 검사 완료",
            "issues": parsed.get("issues") if isinstance(parsed.get("issues"), list) else [],
        })
    except Exception as e:
        result["status"] = "warning"
        result["summary"] = "AI 정밀 검사 실패 또는 Gemini 미설정"
        result["warnings"].append(str(e))
    finally:
        for frame in frames:
            try:
                os.remove(frame)
            except Exception:
                pass
        try:
            if frames:
                os.rmdir(os.path.dirname(frames[0]))
        except Exception:
            pass
    return result


async def run_pre_upload_qa(project_id: int, video_path: str, metadata: Optional[Dict[str, Any]] = None, force_semantic: bool = False) -> Dict[str, Any]:
    settings = get_qa_settings()
    checked_at = _now_iso()
    if not _bool_setting(settings, "qa_enable_pipeline", True):
        result = {"final_status": "skipped", "hold_upload": False, "checked_at": checked_at, "technical": {"status": "skipped"}, "semantic": {"status": "skipped"}}
        _persist_result(project_id, result)
        return result

    technical = run_technical_qa(project_id, video_path, settings)
    hold_upload = False
    if technical.get("status") == "failed" and _bool_setting(settings, "qa_hold_on_technical_fail", True):
        hold_upload = True

    semantic = {"status": "skipped", "summary": "AI 정밀 검사 비활성화"}
    if force_semantic or _bool_setting(settings, "qa_enable_semantic_check", False):
        semantic = await run_semantic_qa(project_id, resolve_upload_video_path(project_id, video_path), metadata, settings)
        if semantic.get("status") == "failed" and _bool_setting(settings, "qa_hold_on_semantic_fail", True):
            hold_upload = True

    if hold_upload:
        final_status = "blocked"
    elif technical.get("status") == "failed" or semantic.get("status") == "failed":
        final_status = "warning"
    elif technical.get("status") == "warning" or semantic.get("status") == "warning":
        final_status = "warning"
    else:
        final_status = "passed"

    result = {
        "technical": technical,
        "semantic": semantic,
        "final_status": final_status,
        "hold_upload": hold_upload,
        "checked_at": checked_at,
    }
    _persist_result(project_id, result)
    if hold_upload:
        db.update_project_setting(project_id, "admin_publish_status", "qa_hold")
    return result


def is_upload_blocked(project_id: int) -> Tuple[bool, Dict[str, Any]]:
    settings = db.get_project_settings(project_id) or {}
    hold = str(settings.get("qa_hold_upload") or "0") in {"1", "true", "True"}
    result_json = settings.get("qa_result_json") or "{}"
    try:
        result = json.loads(result_json)
    except Exception:
        result = {"raw": result_json}
    return hold, result


def resolve_upload_video_path(project_id: int, fallback_path: str) -> str:
    settings = db.get_project_settings(project_id) or {}
    normalized = settings.get("qa_normalized_video_path")
    if normalized and os.path.exists(_to_abs_video_path(normalized)):
        return _to_abs_video_path(normalized)
    return _to_abs_video_path(fallback_path)
