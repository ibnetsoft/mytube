"""
Voicebox TTS API Router (기존 ElevenLabs TTS 라우터(app/routers/tts.py)와 완전히 별개)

- GET  /api/voicebox/health                Voicebox 서버/모델 상태
- GET  /api/voicebox/voices                프로필 + 엔진 프리셋 목록
- POST /api/voicebox/generate              로컬(스튜디오 머신) Voicebox TTS 생성 (단일/멀티보이스)
- POST /api/voicebox/models/download       엔진 모델 다운로드 트리거
- POST /api/voicebox/worker-generate       워커 render_audio 잡 제출 (워커 머신의 Voicebox 사용)
- GET  /api/voicebox/worker-status/{id}    워커 잡 상태 폴링 + 완료 시 프로젝트 TTS로 등록

워커 잡 페이로드 규약:
  remote_render_queue 행의 metadata JSONB 안에 voicebox_tts 스펙을 실어 보낸다
  (auth-web 클레임 라우트가 metadata 컬럼만 워커에 전달하기 때문).
"""
import asyncio
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from config import config
import database as db
from app.utils import get_project_output_dir
from services.voicebox_client import (
    ENGINE_INFO,
    VoiceboxConnectionError,
    VoiceboxError,
    audio_duration_seconds,
    merge_audio_files,
    model_name_for,
    parse_speaker_segments,
    voicebox_client,
    wav_bytes_to_mp3,
)

router = APIRouter(prefix="/api/voicebox", tags=["Voicebox TTS"])


class VoiceboxGenerateRequest(BaseModel):
    text: str
    voice_ref: Optional[str] = None  # "profile:<id>" | "preset:<engine>:<voice_id>"
    engine: Optional[str] = None
    language: Optional[str] = "ko"
    speed: Optional[float] = 1.0
    seed: Optional[int] = None
    project_id: Optional[int] = None
    multi_voice: bool = False
    voice_map: Dict[str, Any] = Field(default_factory=dict)  # {화자: voice_ref}


class VoiceboxModelDownloadRequest(BaseModel):
    engine: str


class VoiceboxWorkerRequest(BaseModel):
    text: str
    voice_ref: Optional[str] = None
    engine: Optional[str] = None
    language: Optional[str] = "ko"
    speed: Optional[float] = 1.0
    seed: Optional[int] = None
    project_id: int
    multi_voice: bool = False
    voice_map: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 상태 / 보이스 목록
# ---------------------------------------------------------------------------
@router.get("/health")
async def voicebox_health():
    """Voicebox 서버 상태 (서버 다운 시에도 200 + reachable=false 로 응답해 UI 표시용으로 사용)."""
    try:
        health = await voicebox_client.check_health()
    except VoiceboxError as e:
        return {"reachable": False, "error": str(e), "engines": ENGINE_INFO}

    profiles_count = 0
    models: list = []
    try:
        profiles = await voicebox_client.list_profiles()
        profiles_count = len(profiles)
    except VoiceboxError:
        pass
    try:
        models = await voicebox_client.list_models()
    except VoiceboxError:
        pass

    # 엔진별 모델 준비 여부 요약
    engine_models = {}
    for engine, info in ENGINE_INFO.items():
        prefix = info["model"]
        matched = [m for m in models if str(m.get("model_name", "")).startswith(prefix)]
        engine_models[engine] = {
            **info,
            "downloaded": any(m.get("downloaded") for m in matched),
            "loaded": any(m.get("loaded") for m in matched),
            "model_names": [m.get("model_name") for m in matched if m.get("model_name")],
        }

    return {
        "reachable": True,
        "health": health,
        "profiles": profiles_count,
        "engines": ENGINE_INFO,
        "engine_models": engine_models,
    }


@router.get("/voices")
async def voicebox_voices():
    """Voicebox 음성 목록 - 기존 프로필 + 엔진 프리셋(자동 프로필 생성 대상)."""
    voices = []

    try:
        profiles = await voicebox_client.list_profiles()
        for p in profiles:
            voices.append({
                "id": f"profile:{p.get('id')}",
                "name": p.get("name") or "이름 없음",
                "kind": "profile",
                "engine": p.get("default_engine") or "",
                "language": p.get("language") or "",
                "voice_type": p.get("voice_type") or "",
            })
    except VoiceboxError as e:
        return {"voices": [], "error": str(e)}

    # 프리셋 (kind=preset - 생성 시 프로필로 자동 변환됨)
    for engine, info in ENGINE_INFO.items():
        try:
            presets = await voicebox_client.list_presets(engine)
        except VoiceboxError:
            continue
        for v in presets:
            voices.append({
                "id": f"preset:{engine}:{v.get('voice_id')}",
                "name": f"{v.get('name')} [{info['label']}]",
                "kind": "preset",
                "engine": engine,
                "language": v.get("language") or "",
                "gender": v.get("gender") or "",
            })

    return {"voices": voices}


# ---------------------------------------------------------------------------
# 모델 다운로드
# ---------------------------------------------------------------------------
@router.post("/models/download")
async def voicebox_model_download(req: VoiceboxModelDownloadRequest):
    """엔진 모델 다운로드 트리거 (qwen 등은 최초 생성 전에 다운로드 필요)."""
    model_name = model_name_for(req.engine)
    if not model_name:
        return {"status": "error", "error": f"알 수 없는 엔진입니다: {req.engine}"}
    try:
        result = await voicebox_client.start_model_download(model_name)
        return {"status": "ok", "model_name": model_name, "result": result}
    except VoiceboxError as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# 로컬 생성 (스튜디오 머신의 Voicebox)
# ---------------------------------------------------------------------------
def _resolve_output_target(project_id: Optional[int], prefix: str = "voicebox_tts"):
    now_kst = config.get_kst_time()
    filename = f"{prefix}_{now_kst.strftime('%Y%m%d_%H%M%S')}.mp3"
    if project_id:
        output_dir, web_dir = get_project_output_dir(project_id)
    else:
        output_dir, web_dir = config.OUTPUT_DIR, "/output"
    result_filename = os.path.normpath(os.path.abspath(os.path.join(output_dir, filename)))
    return output_dir, web_dir, filename, result_filename


def _resolve_request_language(req) -> str:
    if req.language and str(req.language).strip():
        return req.language
    if req.project_id:
        try:
            project = db.get_project(req.project_id) or {}
            settings = db.get_project_settings(req.project_id) or {}
            lang = settings.get("target_language") or project.get("language")
            if lang:
                return lang
        except Exception:
            pass
    return "ko"


async def _generate_segment_mp3(text: str, voice_ref: str, seg_path: str, engine: Optional[str],
                                language: str, speed: float, seed: Optional[int]) -> str:
    """[내부] 세그먼트 1개 생성 - 실패를 호출자에게 전파해 부분 성공 저장을 막는다."""
    resolved = await voicebox_client.resolve_voice_ref(
        voice_ref, default_engine=engine, language=language
    )
    wav_bytes = await voicebox_client.generate_stream(
        text, resolved["profile_id"], engine=resolved["engine"],
        language=language, seed=seed,
    )
    wav_bytes_to_mp3(wav_bytes, seg_path, speed)
    if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
        return seg_path
    raise VoiceboxError("세그먼트 오디오 파일이 생성되지 않았습니다.")


@router.post("/generate")
async def voicebox_generate(req: VoiceboxGenerateRequest):
    """Voicebox TTS 생성 (단일/멀티보이스). 응답 계약은 /api/tts/generate 와 동일."""
    from services.tts_service import tts_service

    start_time = time.time()
    text = str(req.text or "").strip()
    if not text:
        return {"status": "error", "error": "텍스트를 입력해주세요."}

    language = _resolve_request_language(req)
    speed = max(0.5, min(2.0, float(req.speed or 1.0)))
    voice_label = "multi-voice" if (req.multi_voice and req.voice_map) else (req.voice_ref or "default")

    def _log_tts(status: str, error_msg: str = ""):
        try:
            db.add_ai_log(
                req.project_id, "tts", voice_label, "voicebox", status,
                prompt_summary=text[:100],
                error_msg=error_msg,
                elapsed_time=time.time() - start_time,
            )
        except Exception as log_e:
            print(f"[Voicebox TTS] ai_log 기록 실패: {log_e}")

    output_dir, web_dir, filename, result_filename = _resolve_output_target(req.project_id)

    try:
        if req.multi_voice and req.voice_map:
            segments = parse_speaker_segments(text)
            if not segments:
                return {"status": "error", "error": "멀티보이스로 처리할 대본이 없습니다."}

            base_name = os.path.splitext(filename)[0]
            semaphore = asyncio.Semaphore(2)  # 로컬 서버 과부하 방지

            async def process_segment(idx: int, seg: dict) -> str:
                async with semaphore:
                    ref = req.voice_map.get(seg["speaker"]) or req.voice_ref or ""
                    if isinstance(ref, dict):
                        ref = ref.get("id") or ref.get("voice_ref")
                    seg_filename = f"{base_name}_seg_{idx:03d}.mp3"
                    seg_path = os.path.join(output_dir, seg_filename)
                    try:
                        return await _generate_segment_mp3(
                            seg["text"], str(ref or ""), seg_path, req.engine, language, speed, req.seed
                        )
                    except Exception as e:
                        speaker = seg.get("speaker") or f"segment-{idx + 1}"
                        raise VoiceboxError(f"{speaker} 세그먼트 생성 실패: {e}") from e

            print(f"[Voicebox TTS] 멀티보이스 생성 시작 (세그먼트 {len(segments)}개)")
            tasks = [process_segment(i, s) for i, s in enumerate(segments)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            failures = [r for r in results if isinstance(r, Exception)]
            audio_files = [r for r in results if isinstance(r, str)]
            if failures:
                for f in audio_files:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                error_msg = "멀티보이스 일부 세그먼트 생성 실패: " + "; ".join(str(f) for f in failures[:3])
                _log_tts("failed", error_msg)
                return {"status": "error", "error": error_msg}

            if not audio_files:
                error_msg = "생성된 오디오 세그먼트가 없습니다. (Voicebox 서버/보이스 설정 확인)"
                _log_tts("failed", error_msg)
                return {"status": "error", "error": error_msg}

            if len(audio_files) == 1:
                os.replace(audio_files[0], result_filename)
            elif not merge_audio_files(audio_files, result_filename):
                error_msg = "오디오 병합 실패 (Pydub 및 MoviePy 모두 실패)"
                _log_tts("failed", error_msg)
                return {"status": "error", "error": error_msg}

            # 임시 세그먼트 정리
            for f in audio_files:
                if os.path.exists(f) and f != result_filename:
                    try:
                        os.remove(f)
                    except OSError:
                        pass
            output_path = result_filename
        else:
            result = await tts_service.generate_voicebox(
                text,
                voice_ref=req.voice_ref,
                filename=result_filename,
                engine=req.engine,
                language=language,
                speed=speed,
                seed=req.seed,
            )
            output_path = result.get("audio_path")

        if not output_path or not os.path.exists(output_path):
            raise VoiceboxError("오디오 파일이 생성되지 않았습니다.")

        # DB 저장 (기존 TTS 파이프라인과 동일하게 프로젝트에 등록)
        duration = audio_duration_seconds(output_path)
        if req.project_id:
            try:
                db.save_tts(
                    req.project_id,
                    "multi-voice" if req.multi_voice else (req.voice_ref or "default"),
                    "Voicebox Multi Voice" if req.multi_voice else "Voicebox",
                    output_path,
                    duration,
                )
                if text:
                    db.update_project_setting(req.project_id, "script", text)
            except Exception as db_e:
                print(f"[Voicebox TTS] DB 저장 실패: {db_e}")

        final_url = f"{web_dir}/{filename}" if req.project_id else f"/output/{filename}"
        _log_tts("success")
        return {
            "status": "ok",
            "file": filename,
            "url": final_url,
            "full_path": output_path,
            "duration": duration,
        }

    except VoiceboxConnectionError as e:
        _log_tts("failed", str(e))
        return {"status": "error", "error": str(e)}
    except VoiceboxError as e:
        _log_tts("failed", str(e))
        return {"status": "error", "error": str(e)}
    except Exception as e:
        _log_tts("failed", str(e))
        return {"status": "error", "error": f"Voicebox TTS 생성 실패: {e}"}


# ---------------------------------------------------------------------------
# 워커 생성 (워커 머신의 로컬 Voicebox - render_audio 잡)
# ---------------------------------------------------------------------------
@router.post("/worker-generate")
async def voicebox_worker_generate(req: VoiceboxWorkerRequest):
    """워커에 render_audio 잡 제출 (remote_render_queue + metadata.voicebox_tts)."""
    from services.remote_drive_render_service import remote_drive_render_service

    text = str(req.text or "").strip()
    if not text:
        return {"status": "error", "error": "텍스트를 입력해주세요."}

    try:
        result = remote_drive_render_service.enqueue_voicebox_tts(
            project_id=req.project_id,
            tts_spec={
                "text": text,
                "voice_ref": req.voice_ref or "",
                "engine": req.engine or "",
                "language": _resolve_request_language(req),
                "speed": max(0.5, min(2.0, float(req.speed or 1.0))),
                "seed": req.seed,
                "multi_voice": bool(req.multi_voice),
                "voice_map": req.voice_map or {},
            },
        )
        return {"status": "ok", "task_id": result["task_id"]}
    except Exception as e:
        return {"status": "error", "error": f"워커 잡 제출 실패: {e}"}


@router.get("/worker-status/{task_id}")
async def voicebox_worker_status(task_id: str, project_id: Optional[int] = None):
    """워커 잡 상태 조회. 완료 시 오디오를 프로젝트 폴더로 수집해 TTS로 등록한다."""
    from services.remote_drive_render_service import remote_drive_render_service

    try:
        row = remote_drive_render_service.get_queue_row(task_id)
    except Exception as e:
        return {"status": "error", "error": f"잡 상태 조회 실패: {e}"}
    if not row:
        return {"status": "error", "error": "잡을 찾을 수 없습니다."}

    status = str(row.get("status") or "")
    if status != "completed":
        return {
            "status": status or "pending",
            "progress": row.get("progress", 0),
            "message": row.get("message") or row.get("error_message") or "",
        }

    if not project_id:
        return {"status": "completed", "message": "완료", "result_ref": row.get("result_file_id")}

    # 완료 - 결과 수집 (로컬 경로 or Google Drive 파일)
    output_dir, web_dir, filename, local_path = _resolve_output_target(project_id)
    result_ref = str(row.get("result_file_id") or "").strip()
    collected = False

    if result_ref and os.path.exists(result_ref):
        # 워커가 스튜디오와 같은 머신(또는 공유 스토리지)일 때 - 로컬 복사
        import shutil
        try:
            shutil.copy2(result_ref, local_path)
            collected = True
        except OSError as e:
            print(f"[Voicebox TTS] 결과 복사 실패({e}) - Drive 다운로드 시도")
    if not collected and result_ref:
        # Google Drive 파일 ID로 다운로드 (원격 워커 경로)
        try:
            from services.google_drive_service import google_drive_service
            token_path = remote_drive_render_service._get_google_token_path()
            downloaded = google_drive_service.download_file(result_ref, local_path, token_path=token_path)
            collected = bool(downloaded and os.path.exists(local_path))
        except Exception as e:
            print(f"[Voicebox TTS] Drive 다운로드 실패: {e}")

    if not collected or not os.path.exists(local_path):
        return {
            "status": "error",
            "error": f"완료된 결과를 가져올 수 없습니다 (result_ref={result_ref}).",
        }

    duration = audio_duration_seconds(local_path)
    try:
        db.save_tts(project_id, "voicebox_worker", "Voicebox (워커)", local_path, duration)
    except Exception as db_e:
        print(f"[Voicebox TTS] DB 저장 실패: {db_e}")

    return {
        "status": "ok",
        "job_status": "completed",
        "file": filename,
        "url": f"{web_dir}/{filename}" if project_id else f"/output/{filename}",
        "full_path": local_path,
        "duration": duration,
    }
