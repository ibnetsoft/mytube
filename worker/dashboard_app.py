"""
AIR Worker Web Dashboard — FastAPI app with embedded single-page HTML.

Runs inside the Manager process on a separate uvicorn instance bound to
127.0.0.1:3002 (daemon thread).  Reuses the same DPAPI auth token as the
Local API (local_api_token.py) so the user only needs one token.
"""
import json
import time
from pathlib import Path

import job_store
from fastapi import FastAPI, Header, HTTPException, Response
from local_api_token import verify_token
from logging_setup import get_logger
from render_pipeline_adapter import render_status_display
from worker_config import MANAGER_STATUS_FILE, OUTPUT_DIR, WORKER_ID
from hermes_autopilot import CATEGORIES, HermesAutopilotManager

logger = get_logger("dashboard")
app = FastAPI(title="AIR Worker Dashboard")
autopilot_manager = HermesAutopilotManager()

# ---------------------------------------------------------------------------
# Auth helpers (same pattern as local_api_app.py)
# ---------------------------------------------------------------------------

def _token_from_cookie_or_header(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
) -> str | None:
    """Extract bearer token from Authorization header *or* session cookie."""
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer "):]
    if cookie:
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("dashboard_token="):
                return part[len("dashboard_token="):]
    return None


def require_auth(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    # 인증 해제: 바로 통과
    pass


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _read_manager_status() -> dict:
    if not MANAGER_STATUS_FILE.exists():
        return {"processes": {}, "hermes_paused": False, "worker_id": WORKER_ID, "manager_alive": False}
    try:
        data = json.loads(MANAGER_STATUS_FILE.read_text(encoding="utf-8"))
        data["manager_alive"] = (time.time() - data.get("written_at", 0)) < 5
        return data
    except (json.JSONDecodeError, OSError):
        return {"processes": {}, "hermes_paused": False, "worker_id": WORKER_ID, "manager_alive": False}


def _read_job_result(job_id: str) -> dict | None:
    """Read the Hermes result JSON if it exists on disk."""
    result_path = OUTPUT_DIR / "hermes_results" / f"{job_id}.json"
    if result_path.exists():
        try:
            return json.loads(result_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


STYLE_PRESET_TYPES = {"image", "script"}


def _normalize_style_preset(body: dict) -> dict:
    preset_type = str(body.get("preset_type") or "").strip().lower()
    key_code = str(body.get("key_code") or "").strip().lower()
    display_name_ko = str(body.get("display_name_ko") or "").strip()
    prompt_template = str(body.get("prompt_template") or "").strip()
    if preset_type not in STYLE_PRESET_TYPES:
        raise HTTPException(400, "스타일 타입은 image 또는 script만 가능합니다.")
    if not key_code or not key_code.replace("_", "").isalnum():
        raise HTTPException(400, "스타일 코드는 영문, 숫자, 밑줄만 사용할 수 있습니다.")
    if not display_name_ko or not prompt_template:
        raise HTTPException(400, "한글 표시명과 프롬프트 템플릿은 필수입니다.")
    return {
        "preset_type": preset_type,
        "key_code": key_code,
        "display_name_ko": display_name_ko,
        "display_name_vi": str(body.get("display_name_vi") or "").strip(),
        "prompt_template": prompt_template,
        "gemini_instruction": str(body.get("gemini_instruction") or "").strip(),
        "image_url": str(body.get("image_url") or "").strip(),
    }


def _sync_style_preset_to_local(preset: dict) -> None:
    """Keep the Worker generation cache aligned immediately after an edit."""
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    import database as db

    if preset["preset_type"] == "script":
        db.save_script_style_preset(
            preset["key_code"], preset["prompt_template"],
            display_name_ko=preset.get("display_name_ko"),
            display_name_vi=preset.get("display_name_vi"),
        )
    else:
        db.save_style_preset(
            preset["key_code"], preset["prompt_template"],
            image_url=preset.get("image_url") or None,
            gemini_instruction=preset.get("gemini_instruction") or None,
            mode="image",
            display_name_ko=preset.get("display_name_ko"),
            display_name_vi=preset.get("display_name_vi"),
        )


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "time": time.time()}


@app.get("/api/status")
async def api_status(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    snap = _read_manager_status()
    snap["render_status"] = render_status_display()
    return snap


@app.get("/api/jobs")
async def api_jobs(
    status: str | None = None,
    limit: int = 50,
    job_type: str | None = None,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    jobs = job_store.list_jobs(status=status, limit=limit)
    if job_type:
        jobs = [j for j in jobs if j.get("job_type") == job_type]
    return {"jobs": jobs}


@app.get("/api/jobs/{job_id}")
async def api_job_detail(
    job_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    job = job_store.get_job(job_id)
    if not job:
        return {"error": "not found"}
    job["transitions"] = job_store.transition_history(job_id)
    result = _read_job_result(job_id)
    if result:
        job["result"] = result
    return job


@app.post("/api/jobs/submit")
async def api_submit_job(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    job_id = job_store.submit_job(
        job_type=body.get("job_type", "render_video"),
        payload=body.get("payload", {}),
        priority=body.get("priority", 100),
        source="dashboard",
        max_retries=body.get("max_retries", 3),
    )
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/cancel")
async def api_cancel_job(
    job_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("cancel_job", {"job_id": job_id}), timeout=15)


@app.get("/api/logs")
async def api_logs(
    process: str = "manager",
    tail_lines: int = 50,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from worker_config import LOG_FILES
    path = LOG_FILES.get(process)
    if not path or not Path(path).exists():
        return {"error": f"로그를 찾을 수 없습니다: '{process}'", "available": list(LOG_FILES.keys())}
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return {"process": process, "lines": lines[-tail_lines:]}


@app.get("/api/style-presets")
async def api_style_presets(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Read shared image/script presets from the source of truth."""
    require_auth(authorization, cookie)
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    presets = web_admin_client.fetch_style_presets(["image", "script"])
    return {"presets": presets, "shared_store_available": web_admin_client.has_supabase()}


@app.post("/api/style-presets")
async def api_save_style_preset(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Save a shared preset, then immediately update the Worker cache."""
    require_auth(authorization, cookie)
    preset = _normalize_style_preset(body)
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    result = web_admin_client.upsert_style_preset(preset)
    if not result.get("success"):
        raise HTTPException(502, result.get("error") or "중앙 스타일 저장소에 저장하지 못했습니다.")
    saved = result.get("preset") or preset
    # The remote API returns the same fields, but normalize to defend against
    # a partial representation response before writing the local cache.
    saved = {**preset, **{k: v for k, v in saved.items() if v is not None}}
    _sync_style_preset_to_local(saved)
    return {"success": True, "preset": saved}


@app.delete("/api/style-presets/{preset_type}/{key_code}")
async def api_delete_style_preset(
    preset_type: str,
    key_code: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    preset_type = preset_type.strip().lower()
    key_code = key_code.strip().lower()
    if preset_type not in STYLE_PRESET_TYPES or not key_code.replace("_", "").isalnum():
        raise HTTPException(400, "잘못된 스타일 정보입니다.")
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client
    import database as db

    result = web_admin_client.delete_style_preset(key_code)
    if not result.get("success"):
        raise HTTPException(502, result.get("error") or "중앙 스타일 저장소에서 삭제하지 못했습니다.")
    if preset_type == "script":
        db.delete_script_style_preset(key_code)
    else:
        db.delete_style_preset(key_code)
    return {"success": True}


@app.get("/api/category-image-style-mappings")
async def api_category_image_style_mappings(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Return the eight Hermes categories, image catalog, and Worker overrides."""
    require_auth(authorization, cookie)
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    category_rows = web_admin_client.fetch_categories("id,name,default_image_style")
    by_name = {str(row.get("name") or ""): row for row in category_rows}
    styles = web_admin_client.fetch_style_presets(["image"])
    overrides = (autopilot_manager.get_status().get("settings") or {}).get("category_image_style_overrides") or {}
    categories = [
        {
            "id": (by_name.get(name) or {}).get("id"),
            "name": name,
            "automatic_default": (by_name.get(name) or {}).get("default_image_style") or "realistic",
            "manual_override": overrides.get(name),
        }
        for name in CATEGORIES
    ]
    return {
        "categories": categories,
        "styles": styles,
        "shared_store_available": web_admin_client.has_supabase(),
    }


@app.put("/api/category-image-style-mappings/{category}")
async def api_save_category_image_style_mapping(
    category: str,
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Save a Worker manual override; it takes precedence over AI selection."""
    require_auth(authorization, cookie)
    if category not in CATEGORIES:
        raise HTTPException(404, "지원하지 않는 Hermes 카테고리입니다.")
    from worker_config import ensure_project_root_on_path
    ensure_project_root_on_path()
    from services.web_admin_client import web_admin_client

    style_key = str(body.get("image_style") or "").strip().lower()
    styles = web_admin_client.fetch_style_presets(["image"])
    allowed_keys = {str(style.get("key_code") or "").strip().lower() for style in styles}
    if style_key and style_key not in allowed_keys:
        raise HTTPException(400, "등록되지 않은 이미지 스타일입니다.")

    result = await autopilot_manager.save_category_image_style_override(category, style_key or None)
    if not result.get("success"):
        raise HTTPException(400, result.get("error") or "이미지 스타일 매칭을 저장하지 못했습니다.")
    return {"success": True, "manual_override": result.get("override")}


@app.post("/api/processes/hermes/start")
async def api_hermes_start(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("start_process", {"name": "hermes_worker"}))


@app.post("/api/processes/hermes/stop")
async def api_hermes_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("stop_process", {"name": "hermes_worker"}))


@app.post("/api/processes/render/start")
async def api_render_start(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("start_process", {"name": "render_worker"}))


@app.post("/api/processes/render/stop")
async def api_render_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("stop_process", {"name": "render_worker"}))


@app.post("/api/processes/remote-drive/start")
async def api_remote_drive_start(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("start_process", {"name": "remote_drive_worker"}))


@app.post("/api/processes/remote-drive/stop")
async def api_remote_drive_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from ipc import submit_command, wait_for_result
    return wait_for_result(submit_command("stop_process", {"name": "remote_drive_worker"}))


# ---------------------------------------------------------------------------
# YouTube Explore API endpoints (proxy to YouTube Data API v3 + Gemini)
# ---------------------------------------------------------------------------

@app.post("/api/yt/search")
async def yt_search(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """YouTube 검색 프록시"""
    require_auth(authorization, cookie)
    from config import Config
    import httpx
    if not Config.YOUTUBE_API_KEY:
        return {"error": "YOUTUBE_API_KEY이 설정되지 않았습니다"}
    params = {
        "part": "snippet",
        "q": body.get("query", ""),
        "type": "video",
        "maxResults": min(body.get("max_results", 10), 25),
        "order": body.get("order", "relevance"),
        "key": Config.YOUTUBE_API_KEY,
    }
    if body.get("published_after"):
        params["publishedAfter"] = body["published_after"]
    if body.get("relevance_language"):
        params["relevanceLanguage"] = body["relevance_language"]
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{Config.YOUTUBE_BASE_URL}/search", params=params)
        if r.status_code != 200:
            err = r.json().get("error", {})
            return {"error": err.get("message", "YouTube API Error")}
        return r.json()


@app.get("/api/yt/videos/{video_id}")
async def yt_videos(
    video_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """YouTube 영상 상세 정보 프록시"""
    require_auth(authorization, cookie)
    from config import Config
    import httpx
    if not Config.YOUTUBE_API_KEY:
        return {"error": "YOUTUBE_API_KEY이 설정되지 않았습니다"}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{Config.YOUTUBE_BASE_URL}/videos",
            params={"part": "snippet,statistics,contentDetails", "id": video_id, "key": Config.YOUTUBE_API_KEY},
        )
        if r.status_code != 200:
            err = r.json().get("error", {})
            return {"error": err.get("message", "YouTube API Error")}
        return r.json()


@app.get("/api/yt/channel/{channel_id}")
async def yt_channel(
    channel_id: str,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """YouTube 채널 정보 프록시"""
    require_auth(authorization, cookie)
    from config import Config
    import httpx
    if not Config.YOUTUBE_API_KEY:
        return {"error": "YOUTUBE_API_KEY이 설정되지 않았습니다"}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{Config.YOUTUBE_BASE_URL}/channels",
            params={"part": "snippet,statistics", "id": channel_id, "key": Config.YOUTUBE_API_KEY},
        )
        if r.status_code != 200:
            err = r.json().get("error", {})
            return {"error": err.get("message", "YouTube API Error")}
        return r.json()


@app.get("/api/yt/trending-keywords")
async def yt_trending_keywords(
    language: str = "ko",
    period: str = "now",
    age: str = "all",
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    """Gemini 기반 트렌드 키워드 생성 (버블 차트용)"""
    require_auth(authorization, cookie)
    from config import Config
    import httpx
    import re as _re
    if not Config.GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY이 설정되지 않았습니다"}
    lang_map = {"ko": "South Korea (Korean)", "ja": "Japan (Japanese)", "en": "USA/International (English)"}
    period_map = {"now": "REAL-TIME / NOW", "week": "THIS WEEK (Last 7 days)", "month": "THIS MONTH (Last 30 days)"}
    age_map = {"all": "ALL Ages", "10s": "Teenagers (10-19)", "20s": "Young Adults (20-29)", "30s": "Adults (30-39)", "40s": "Middle-aged (40+)"}
    lang_name = lang_map.get(language, "South Korea (Korean)")
    period_text = period_map.get(period, "REAL-TIME / NOW")
    age_text = age_map.get(age, "ALL Ages")
    prompt = (
        f"Act as a Local Trend Analyst and YouTube SEO Expert for the specific region: {lang_name}.\n\n"
        f"Generate a list of 20-30 CURRENT trending search keywords/topics on YouTube specifically for:\n"
        f"- Region/Language: {lang_name}\n"
        f"- Time Period: {period_text}\n"
        f"- Target Age Group: {age_text}\n\n"
        f'STRICT LANGUAGE RULES:\n'
        f'1. "keyword": MUST be in the target language ({language}). NOT English (unless English region).\n'
        f'2. "translation": MUST be the meaning in KOREAN (Hangul).\n\n'
        f"DISTRIBUTION RULES:\n"
        f"- Assign a 'volume' score (1-100) using a Power Law distribution.\n"
        f"- 1-2 keywords: 95-100 (Viral)\n"
        f"- 3-5 keywords: 70-90 (High)\n"
        f"- Rest: 20-60 (Moderate)\n\n"
        f'OUTPUT FORMAT (JSON List):\n'
        f'[{{"keyword": "Keyword in Target Language", "translation": "한국어 뜻 설명", "volume": 98, "category": "Gaming"}}, ...]\n\n'
        f"RETURN ONLY THE JSON LIST. NO MARKDOWN."
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={Config.GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.9}},
            )
            if r.status_code != 200:
                return {"error": f"Gemini API 오류: {r.status_code}"}
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            match = _re.search(r'\[[\s\S]*\]', text)
            if match:
                return {"status": "ok", "keywords": json.loads(match.group(0))}
            return {"status": "ok", "keywords": []}
    except Exception as e:
        logger.error(f"trending-keywords error: {e}")
        return {"status": "ok", "keywords": []}


# ---------------------------------------------------------------------------
# Settings endpoints (Hermes / AI API keys)
# ---------------------------------------------------------------------------

# 키 값은 마스킹해서 응답
_MASKED = "••••••••"

def _mask_value(v: str) -> str:
    if not v:
        return ""
    if len(v) <= 8:
        return _MASKED
    return v[:4] + _MASKED


@app.get("/api/settings")
async def api_get_settings(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    from config import Config
    keys = [
        ("GEMINI_API_KEY", "Gemini API 키"),
        ("CLAUDE_API_KEY", "Claude API 키"),
        ("YOUTUBE_API_KEY", "YouTube Data API 키"),
        ("ELEVENLABS_API_KEY", "ElevenLabs API 키"),
        ("SUNO_API_KEY", "Suno API 키"),
        ("TOPIC_GENERATION_MODEL", "주제 생성 모델"),
        ("SCRIPT_GENERATION_MODEL", "대본 생성 모델"),
        ("SCRIPT_PLANNING_MODEL", "대본 구조 모델"),
    ]
    result = []
    for attr, label in keys:
        val = getattr(Config, attr, "")
        is_key = "KEY" in attr
        result.append({"key": attr, "label": label, "value": _mask_value(val), "set": bool(val)})
    return {"settings": result}


@app.post("/api/settings")
async def api_set_setting(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    key = (body.get("key") or "").strip()
    value = (body.get("value") or "").strip()
    if not key:
        return {"error": "key가 필요합니다"}
    
    # 보안: 마스킹된 값이 그대로 들어오면 변경하지 않음 (API 키 계열만 해당)
    is_key = "KEY" in key
    if is_key and (value == _MASKED or value.startswith(_MASKED)):
        return {"ok": True, "message": "변경 없음 (마스킹된 값)"}
        
    allowed = {
        "GEMINI_API_KEY", "CLAUDE_API_KEY", "YOUTUBE_API_KEY",
        "ELEVENLABS_API_KEY", "SUNO_API_KEY",
        "TOPIC_GENERATION_MODEL", "SCRIPT_GENERATION_MODEL", "SCRIPT_PLANNING_MODEL",
    }
    if key not in allowed:
        return {"error": f"허용되지 않은 설정 키: {key}"}
    try:
        from config import Config
        Config.update_api_key(key, value)
        logger.info(f"설정 변경 (대시보드): {key} = {value if 'KEY' not in key else '••••'}")
        
        # Supabase 원격 동시 저장 시도 (Dual-write)
        try:
            from services.web_admin_client import web_admin_client
            sb_key = None
            for k, v in web_admin_client.KEY_MAP.items():
                if v == key:
                    sb_key = k
                    break
            
            if sb_key and web_admin_client.has_supabase():
                # bool 값일 경우 문자열로 형변환해서 전송
                str_val = str(value).lower() if isinstance(value, bool) else str(value)
                ok = web_admin_client.save_global_setting(sb_key, str_val)
                if ok:
                    logger.info(f"Supabase 원격 동기화 완료: {sb_key} = {str_val}")
                else:
                    logger.warning(f"Supabase 원격 동기화 실패 (응답 에러): {sb_key}")
        except Exception as sb_err:
            logger.warning(f"Supabase 원격 저장 실패 (로컬 저장은 유지됨): {sb_err}")
            
        return {"ok": True, "message": f"{key} 저장 완료 (원격 동기화 시도 완료)"}
    except Exception as e:
        logger.error(f"설정 저장 실패: {key} — {e}")
        return {"error": f"저장 실패: {e}"}


# ---------------------------------------------------------------------------
# Hermes Autopilot endpoints
# ---------------------------------------------------------------------------

@app.get("/api/autopilot/hermes/status")
async def api_autopilot_status(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    return autopilot_manager.get_status()


@app.post("/api/autopilot/hermes/start")
async def api_autopilot_start(
    body: dict = None,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    custom_settings = body.get("settings") if body else None
    return await autopilot_manager.start(custom_settings)


@app.post("/api/autopilot/hermes/save_settings")
async def api_autopilot_save_settings(
    body: dict,
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    new_settings = body.get("settings")
    if not new_settings:
        return {"error": "settings가 필요합니다"}
    return await autopilot_manager.save_settings(new_settings)


@app.post("/api/autopilot/hermes/stop")
async def api_autopilot_stop(
    authorization: str | None = Header(default=None),
    cookie: str | None = Header(default=None, alias="Cookie"),
):
    require_auth(authorization, cookie)
    autopilot_result = await autopilot_manager.stop()
    from ipc import submit_command, wait_for_result
    worker_result = wait_for_result(submit_command("stop_process", {"name": "hermes_worker"}))
    cancelled_jobs = job_store.cancel_nonterminal_jobs_by_source(
        "autopilot",
        reason="autopilot stopped by administrator",
    )
    return {
        "success": bool(worker_result.get("success")),
        "autopilot_was_running": bool(autopilot_result.get("success")),
        "cancelled_job_count": len(cancelled_jobs),
    }


# ---------------------------------------------------------------------------
# Login page (serves HTML — no auth required)
# ---------------------------------------------------------------------------

@app.get("/login")
async def login_page():
    return Response(content=LOGIN_HTML, media_type="text/html; charset=utf-8")


@app.post("/auth/login")
async def auth_login(body: dict, response: Response):
    token = (body.get("token") or "").strip()
    if not verify_token(token):
        return {"error": "토큰이 올바르지 않습니다"}
    response = Response(
        content='{"ok":true}',
        media_type="application/json",
        headers={"Set-Cookie": f"dashboard_token={token}; Path=/; SameSite=Strict; Max-Age=604800"},
    )
    return response


@app.post("/auth/logout")
async def auth_logout(response: Response):
    return Response(
        content='{"ok":true}',
        media_type="application/json",
        headers={"Set-Cookie": "dashboard_token=; Path=/; SameSite=Strict; Max-Age=0"},
    )


# ---------------------------------------------------------------------------
# Dashboard single-page HTML (embedded as a Python string)
# ---------------------------------------------------------------------------

@app.get("/")
async def dashboard_page():
    return Response(content=DASHBOARD_HTML, media_type="text/html; charset=utf-8")


# =========================================================================
# HTML templates (login + dashboard)
# =========================================================================

LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIR Worker — 로그인</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0f1117; color: #e1e4e8; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
.login-box { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 40px; width: 400px; max-width: 90vw; }
.login-box h1 { font-size: 24px; margin-bottom: 8px; }
.login-box p { color: #8b949e; margin-bottom: 24px; font-size: 14px; }
input { width: 100%; padding: 10px 14px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #e1e4e8; font-size: 14px; outline: none; }
input:focus { border-color: #58a6ff; }
button { width: 100%; padding: 10px; border: none; border-radius: 6px; background: #238636; color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 16px; }
button:hover { background: #2ea043; }
.error { color: #f85149; font-size: 13px; margin-top: 12px; display: none; }
</style>
</head>
<body>
<div class="login-box">
  <h1>AIR Worker</h1>
  <p>대시보드에 접근하려면 인증 토큰을 입력하세요.</p>
  <input type="password" id="token-input" placeholder="인증 토큰" autocomplete="off">
  <button onclick="login()">로그인</button>
  <div class="error" id="error-msg"></div>
</div>
<script>
async function login() {
  const token = document.getElementById('token-input').value.trim();
  const errEl = document.getElementById('error-msg');
  errEl.style.display = 'none';
  try {
    const res = await fetch('/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token})
    });
    const data = await res.json();
    if (data.error) { errEl.textContent = data.error; errEl.style.display = 'block'; return; }
    window.location.href = '/';
  } catch(e) { errEl.textContent = '서버 오류'; errEl.style.display = 'block'; }
}
document.getElementById('token-input').addEventListener('keydown', e => { if(e.key==='Enter') login(); });
</script>
</body>
</html>"""


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIR Worker — 대시보드</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
/* ── Reset & Base ── */
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0d1117; color: #c9d1d9; font-size: 14px; line-height: 1.5; }
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #161b22; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }

/* ── Layout ── */
.app { display: flex; height: 100vh; }
.sidebar { width: 220px; background: #161b22; border-right: 1px solid #21262d; display: flex; flex-direction: column; flex-shrink: 0; }
.sidebar-brand { padding: 20px 16px; border-bottom: 1px solid #21262d; }
.sidebar-brand h1 { font-size: 18px; font-weight: 700; }
.sidebar-brand span { font-size: 12px; color: #8b949e; }
.nav { flex: 1; padding: 12px 8px; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 6px; cursor: pointer; color: #8b949e; transition: all 0.15s; }
.nav-item:hover { background: #21262d; color: #c9d1d9; }
.nav-item.active { background: #1f6feb22; color: #58a6ff; font-weight: 600; }
.nav-item .icon { font-size: 18px; width: 24px; text-align: center; }
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.topbar { padding: 12px 24px; border-bottom: 1px solid #21262d; display: flex; align-items: center; justify-content: space-between; background: #161b22; }
.topbar h2 { font-size: 16px; font-weight: 600; }
.topbar-actions { display: flex; align-items: center; gap: 12px; }
.refresh-indicator { font-size: 12px; color: #8b949e; }
.content { flex: 1; overflow-y: auto; padding: 24px; }

/* ── Cards ── */
.card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.card-title { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }

/* ── Status Cards Grid ── */
.status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
.status-card { background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px; }
.status-card .name { font-size: 16px; font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.status-card .info { font-size: 12px; color: #8b949e; }
.status-card .progress-bar { height: 4px; background: #21262d; border-radius: 2px; margin-top: 10px; overflow: hidden; }
.status-card .progress-fill { height: 100%; background: #238636; border-radius: 2px; transition: width 0.3s; }

/* ── Badges ── */
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.badge-running { background: #23863622; color: #3fb950; }
.badge-idle { background: #8b949e22; color: #8b949e; }
.badge-stopped { background: #f8514922; color: #f85149; }
.badge-starting { background: #d2992222; color: #d29922; }
.badge-disabled { background: #f8514922; color: #f85149; }
.badge-queued { background: #8b949e22; color: #8b949e; }
.badge-claimed { background: #d2992222; color: #d29922; }
.badge-preparing { background: #1f6feb22; color: #58a6ff; }
.badge-rendering { background: #23863622; color: #3fb950; }
.badge-uploading { background: #a371f722; color: #a371f7; }
.badge-completed { background: #23863622; color: #3fb950; }
.badge-failed { background: #f8514922; color: #f85149; }
.badge-canceled { background: #f8514922; color: #f85149; }
.badge-abandoned { background: #f8514922; color: #f85149; }

/* ── Tables ── */
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #21262d; }
th { color: #8b949e; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
td { font-size: 13px; }
tr:hover { background: #161b22; }

/* ── Buttons ── */
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border: 1px solid #30363d; border-radius: 6px; background: #21262d; color: #c9d1d9; font-size: 13px; cursor: pointer; transition: all 0.15s; }
.btn:hover { background: #30363d; }
.btn-primary { background: #238636; border-color: #238636; color: #fff; }
.btn-primary:hover { background: #2ea043; }
.btn-danger { background: #da3633; border-color: #da3633; color: #fff; }
.btn-danger:hover { background: #f85149; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-start { border-color: #238636; color: #3fb950; }
.btn-start:hover:not(:disabled) { background: #23863622; }
.btn-stop { border-color: #da3633; color: #f85149; }
.btn-stop:hover:not(:disabled) { background: #da363322; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Forms ── */
.form-group { margin-bottom: 16px; }
.form-group label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 6px; font-weight: 500; }
.form-group input, .form-group select, .form-group textarea {
  width: 100%; padding: 8px 12px; border: 1px solid #30363d; border-radius: 6px;
  background: #0d1117; color: #c9d1d9; font-size: 14px; outline: none;
}
.form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: #58a6ff; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* ── Log viewer ── */
.log-viewer { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 12px; font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: 12px; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; color: #8b949e; }

/* ── Tab content ── */
.tab-content { display: none; }
.tab-content.active { display: block; }

/* ── Job detail modal ── */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 100; justify-content: center; align-items: center; }
.modal-overlay.active { display: flex; }
.modal { background: #161b22; border: 1px solid #21262d; border-radius: 12px; width: 700px; max-width: 90vw; max-height: 80vh; overflow-y: auto; padding: 24px; }
.modal h3 { margin-bottom: 16px; }
.modal .close { float: right; cursor: pointer; color: #8b949e; font-size: 20px; }

/* ── YouTube Explore Tab ── */
.yt-filter-row { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.yt-lang-btn.active { background: #1f6feb22; border-color: #58a6ff; color: #58a6ff; }
.yt-search-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.yt-search-row input { flex: 1; min-width: 200px; padding: 8px 12px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #c9d1d9; font-size: 14px; outline: none; }
.yt-search-row input:focus { border-color: #58a6ff; }
.yt-search-row select { padding: 8px 12px; border: 1px solid #30363d; border-radius: 6px; background: #0d1117; color: #c9d1d9; font-size: 13px; outline: none; }
.yt-tag { display: inline-block; padding: 4px 10px; border-radius: 14px; font-size: 12px; cursor: pointer; background: #21262d; color: #8b949e; border: 1px solid #30363d; transition: all 0.15s; }
.yt-tag:hover { background: #1f6feb22; border-color: #58a6ff; color: #58a6ff; }
.bubble-loading { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: #161b22cc; color: #8b949e; font-size: 14px; z-index: 5; border-radius: 8px; }
.yt-thumb { width: 120px; height: 68px; border-radius: 4px; object-fit: cover; background: #21262d; }
.yt-channel-avatar { width: 32px; height: 32px; border-radius: 50%; object-fit: cover; margin-right: 6px; vertical-align: middle; }
.yt-title-cell { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.yt-viral-score { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.yt-viral-high { background: #23863622; color: #3fb950; }
.yt-viral-mid { background: #d2992222; color: #d29922; }
.yt-viral-low { background: #8b949e22; color: #8b949e; }
.yt-analysis-text { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 16px; font-size: 13px; line-height: 1.8; color: #c9d1d9; white-space: pre-wrap; max-height: 400px; overflow-y: auto; margin-top: 12px; }
.yt-stat { font-size: 11px; color: #8b949e; margin-top: 2px; }

/* ── Timeline ── */
.timeline { border-left: 2px solid #21262d; padding-left: 20px; margin: 16px 0; }
.timeline-item { position: relative; padding: 8px 0; font-size: 13px; }
.timeline-item::before { content: ''; position: absolute; left: -26px; top: 14px; width: 10px; height: 10px; border-radius: 50%; background: #58a6ff; border: 2px solid #0d1117; }
.timeline-item .time { color: #8b949e; font-size: 11px; }

/* ── Notification toast ── */
.toast-container { position: fixed; top: 20px; right: 20px; z-index: 200; display: flex; flex-direction: column; gap: 8px; }
.toast { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; font-size: 13px; animation: slideIn 0.3s ease; }
.toast.success { border-left: 3px solid #3fb950; }
.toast.error { border-left: 3px solid #f85149; }
.toast.warning { border-left: 3px solid #d29922; }
.toast.info { border-left: 3px solid #58a6ff; }
@keyframes slideIn { from { opacity: 0; transform: translateX(40px); } to { opacity: 1; transform: translateX(0); } }

/* ── Empty state ── */
.empty { text-align: center; padding: 40px; color: #8b949e; }
.empty .icon { font-size: 48px; margin-bottom: 12px; }

/* ── Settings tab ── */
.setting-row:last-child { border-bottom: none !important; }
.setting-input:focus { border-color: #58a6ff !important; box-shadow: 0 0 0 2px rgba(88,166,255,0.15); }
.setting-input::placeholder { color: #484f58; }

/* ── Result viewer ── */
.result-viewer { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 12px; font-size: 13px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; }
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-brand">
      <h1>AIR Worker</h1>
      <span>대시보드</span>
    </div>
    <div class="nav">
      <div class="nav-item active" data-tab="overview" onclick="switchTab('overview')">
        <span class="icon">&#x1F4CA;</span> 대시보드
      </div>
      <div class="nav-item" data-tab="rendering" onclick="switchTab('rendering')">
        <span class="icon">&#x1F3AC;</span> 렌더링 상황
      </div>
      <div class="nav-item" data-tab="topic-search" onclick="switchTab('topic-search')">
        <span class="icon">&#x1F50D;</span> 주제 찾기
      </div>
      <div class="nav-item" data-tab="yt-explore" onclick="switchTab('yt-explore')">
        <span class="icon">&#x1F30D;</span> YouTube 탐색
      </div>
      <div class="nav-item" data-tab="hermes-autopilot" onclick="switchTab('hermes-autopilot')">
        <span class="icon">&#x1F916;</span> Hermes 자동 생성
      </div>
      <div class="nav-item" data-tab="hermes-gen" onclick="switchTab('hermes-gen')">
        <span class="icon">&#x1F4DD;</span> Hermes 주제 생성
      </div>
      <div class="nav-item" data-tab="styles" onclick="switchTab('styles')">
        <span class="icon">&#x1F3A8;</span> 스타일 관리
      </div>
      <div class="nav-item" data-tab="category-image-styles" onclick="switchTab('category-image-styles')">
        <span class="icon">&#x1F5BC;</span> 카테고리 이미지 스타일
      </div>
      <div class="nav-item" data-tab="history" onclick="switchTab('history')">
        <span class="icon">&#x1F4CB;</span> 작업 히스토리
      </div>
      <div class="nav-item" data-tab="logs" onclick="switchTab('logs')">
        <span class="icon">&#x1F4C4;</span> 로그
      </div>
      <div class="nav-item" data-tab="settings" onclick="switchTab('settings')">
        <span class="icon">&#x2699;</span> 설정
      </div>
    </div>
  </div>

  <!-- Main content -->
  <div class="main">
    <div class="topbar">
      <h2 id="page-title">대시보드</h2>
      <div class="topbar-actions">
        <span class="refresh-indicator" id="refresh-timer"></span>
        <button class="btn btn-sm" onclick="refreshAll()">&#x1F504; 새로고침</button>
        <button class="btn btn-sm" onclick="doLogout()">로그아웃</button>
      </div>
    </div>

    <div class="content">
      <!-- ═══ Tab: Overview ═══ -->
      <div class="tab-content active" id="tab-overview">
        <div class="status-grid" id="process-cards"></div>
        <div class="card">
          <div class="card-title">최근 작업</div>
          <table>
            <thead><tr><th>ID</th><th>유형</th><th>상태</th><th>진행률</th><th>생성시간</th></tr></thead>
            <tbody id="recent-jobs-body"></tbody>
          </table>
          <div class="empty" id="recent-empty" style="display:none"><div class="icon">&#x1F4ED;</div>아직 작업이 없습니다</div>
        </div>
      </div>

      <!-- ═══ Tab: Rendering ═══ -->
      <div class="tab-content" id="tab-rendering">
        <div class="card" id="render-active-card">
          <div class="card-title">현재 렌더 작업</div>
          <div id="render-active-content"></div>
        </div>
        <div class="card">
          <div class="card-title">렌더 작업 목록</div>
          <table>
            <thead><tr><th>ID</th><th>상태</th><th>진행률</th><th>메시지</th><th>시작</th><th>작업</th></tr></thead>
            <tbody id="render-jobs-body"></tbody>
          </table>
          <div class="empty" id="render-empty" style="display:none"><div class="icon">&#x1F3AC;</div>렌더 작업이 없습니다</div>
        </div>
      </div>

      <!-- ═══ Tab: Topic Search ═══ -->
      <div class="tab-content" id="tab-topic-search">
        <div class="card">
          <div class="card-title">&#x1F50D; 주제 찾기</div>
          <p class="info" style="margin:-4px 0 16px">관심 키워드와 시청자 반응을 살펴볼 콘텐츠 주제를 찾습니다.</p>
          <div class="form-row">
            <div class="form-group">
              <label>키워드 *</label>
              <input type="text" id="tr-keyword" placeholder="예: 인공지능">
            </div>
            <div class="form-group">
              <label>언어</label>
              <select id="tr-language">
                <option value="ko">한국어</option>
                <option value="en">영어</option>
                <option value="ja">日本語</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>국가/시장</label>
              <input type="text" id="tr-country" placeholder="예: KR, US (비워두면 전체 시장)" value="">
            </div>
            <div class="form-group">
              <label>주제 개수</label>
              <input type="number" id="tr-count" min="1" max="30" value="10">
            </div>
          </div>
          <button class="btn btn-primary" onclick="submitTopicResearch()">주제 찾기</button>
        </div>

        <div class="card" style="margin-top:16px">
          <div class="card-title">&#x1F4C8; 고성과 영상 분석</div>
          <p class="info" style="margin:-4px 0 16px">YouTube에서 잘 된 영상의 제목, 구성, 반응을 분석해 기획에 활용합니다.</p>
          <div class="form-row">
            <div class="form-group">
              <label>키워드 *</label>
              <input type="text" id="ba-keyword" placeholder="예: 인공지능">
            </div>
            <div class="form-group">
              <label>비디오 타입</label>
              <select id="ba-video-type">
                <option value="longform">롱폼</option>
                <option value="shorts">쇼츠</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>언어</label>
              <select id="ba-language">
                <option value="ko">한국어</option>
                <option value="en">영어</option>
                <option value="ja">日本語</option>
              </select>
            </div>
            <div class="form-group">
              <label>분석 대상 수</label>
              <input type="number" id="ba-max-candidates" min="1" max="3" value="1">
            </div>
          </div>
          <button class="btn btn-primary" onclick="submitBenchmark()">벤치마크 분석</button>
        </div>
      </div>

      <!-- ═══ Tab: Hermes Generation ═══ -->
      <div class="tab-content" id="tab-hermes-gen">
        <div class="card">
          <div class="card-title">&#x1F4DD; 대본 기획 생성</div>
          <p class="info" style="margin:-4px 0 16px">제목에서 출발해 첫 훅, 장면별 전개, 결말까지의 설계를 만듭니다.</p>
          <div class="form-group">
            <label>주제 *</label>
            <input type="text" id="sp-topic" placeholder="예: 인공지능의 미래">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>대상 길이 (초)</label>
              <input type="number" id="sp-duration" min="15" value="600">
            </div>
            <div class="form-group">
              <label>대본 스타일</label>
              <select id="sp-style"><option value="default">기본</option></select>
            </div>
          </div>
          <div class="form-group">
            <label>언어</label>
            <select id="sp-language">
              <option value="ko">한국어</option>
              <option value="en">영어</option>
              <option value="ja">日本語</option>
            </select>
          </div>
          <button class="btn btn-primary" onclick="submitScriptPlan()">구조 생성</button>
        </div>

        <div class="card" style="margin-top:16px">
          <div class="card-title">&#x1F4AC; 대본 생성</div>
          <p class="info" style="margin:-4px 0 16px">기획을 바탕으로 대본을 작성한 뒤, 흐름과 몰입도를 검수합니다.</p>
          <div class="form-group">
            <label>주제 *</label>
            <input type="text" id="sg-topic" placeholder="예: 인공지능의 미래">
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>대상 길이 (초)</label>
              <input type="number" id="sg-duration" min="15" value="600">
            </div>
            <div class="form-group">
              <label>나레이션 모드</label>
              <select id="sg-narration-mode">
                <option value="single">1인 (단일)</option>
                <option value="dramatic_single" selected>극적 1인 (중간)</option>
                <option value="multi">다인 (멀티)</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>대본 스타일</label>
            <select id="sg-style"><option value="default">기본</option></select>
          </div>
          <div class="form-group">
            <label>장면 구성 (비워두면 주제로 자동 기획)</label>
            <textarea id="sg-structure" rows="4" placeholder='{"scenes": [{"scene_summary": "...", "scene_situation": "..."}]}'></textarea>
          </div>
          <button class="btn btn-primary" onclick="submitScriptGenerate()">대본 생성</button>
        </div>
      </div>

      <!-- ═══ Tab: History ═══ -->
      <div class="tab-content" id="tab-history">
        <div class="card">
          <div class="card-title">필터</div>
          <div class="form-row">
            <div class="form-group">
              <label>상태</label>
              <select id="hist-filter-status" onchange="loadHistory()">
                <option value="">전체</option>
                <option value="QUEUED">대기 중</option>
                <option value="CLAIMED">작업 준비</option>
                <option value="PREPARING">준비 중</option>
                <option value="RENDERING">처리 중</option>
                <option value="UPLOADING">결과 저장 중</option>
                <option value="COMPLETED">완료</option>
                <option value="FAILED">실패</option>
                <option value="CANCELED">취소됨</option>
              </select>
            </div>
            <div class="form-group">
              <label>작업 유형</label>
              <select id="hist-filter-type" onchange="loadHistory()">
                <option value="">전체</option>
                <option value="render_video">영상 렌더링</option>
                <option value="topic_research">주제 탐색</option>
                <option value="topic_benchmark_analyze">고성과 영상 분석</option>
                <option value="web_research">Gemini 웹 자료 조사</option>
                <option value="script_plan_generate">대본 기획 생성</option>
                <option value="script_generate">대본 생성</option>
              </select>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">작업 목록</div>
          <table>
            <thead><tr><th>ID</th><th>유형</th><th>상태</th><th>진행률</th><th>생성시간</th><th>작업</th></tr></thead>
            <tbody id="history-body"></tbody>
          </table>
          <div class="empty" id="history-empty" style="display:none"><div class="icon">&#x1F4CB;</div>작업이 없습니다</div>
        </div>
      </div>

      <!-- ═══ Tab: Logs ═══ -->
      <div class="tab-content" id="tab-logs">
        <div class="card">
          <div class="form-row" style="align-items: end;">
            <div class="form-group">
              <label>프로세스</label>
              <select id="log-process" onchange="loadLogs()">
                <option value="manager">작업 관리자</option>
                <option value="render_worker">영상 작업 Worker</option>
                <option value="remote_drive_worker">Drive API Render Worker</option>
                <option value="hermes_worker">AI 기획·대본 Worker</option>
                <option value="local_api">앱 연결 API</option>
                <option value="dashboard">대시보드</option>
              </select>
            </div>
            <button class="btn" onclick="loadLogs()">로그 불러오기</button>
          </div>
        </div>
        <div class="card">
          <div class="card-title">로그 출력</div>
          <div class="log-viewer" id="log-output">로그를 불러오는 중...</div>
        </div>
      </div>

      <!-- ═══ Tab: Settings ═══ -->
      <div class="tab-content" id="tab-settings">
        <div class="card">
          <div class="card-title">&#x2699; Hermes / AI API 설정</div>
          <p style="color:#8b949e;margin-bottom:16px;font-size:13px;">
            웹 어드민에서 설정한 값도 사용되지만, 여기서 직접 입력하면 로컬 .env 파일에 저장되어 즉시 적용됩니다.
            빈칸으로 두면 웹 어드민 값이 우선 적용됩니다.
          </p>
          <div id="settings-list"></div>
          <div style="margin-top:20px;display:flex;gap:12px;align-items:center;">
            <button class="btn btn-primary" onclick="saveAllSettings()">모든 변경사항 저장</button>
            <button class="btn" onclick="loadSettings()">다시 불러오기</button>
            <span id="settings-status" style="font-size:13px;color:#8b949e"></span>
          </div>
        </div>
      </div>

      <!-- ═══ Tab: Style Presets ═══ -->
      <div class="tab-content" id="tab-styles">
        <div class="card">
          <div class="card-title">&#x1F3A8; 이미지·대본 스타일 프리셋</div>
          <p class="info" style="margin:-4px 0 16px">여기서 저장한 스타일은 중앙 저장소와 AI Worker에 즉시 함께 반영됩니다. 대본 스타일은 다음 대본 기획과 생성 프롬프트에 그대로 적용됩니다.</p>
          <input type="hidden" id="style-edit-key">
          <div class="form-row">
            <div class="form-group">
              <label>스타일 타입 *</label>
              <select id="style-preset-type" onchange="updateStyleFormHelp()">
                <option value="image">이미지 스타일</option>
                <option value="script">대본 스타일</option>
              </select>
            </div>
            <div class="form-group">
              <label>스타일 코드 *</label>
              <input id="style-key-code" type="text" placeholder="예: realistic 또는 historical_drama">
            </div>
            <div class="form-group">
              <label>한글 표시명 *</label>
              <input id="style-name-ko" type="text" placeholder="예: 실사 영화풍">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>베트남어 표시명</label>
              <input id="style-name-vi" type="text" placeholder="선택 사항">
            </div>
            <div class="form-group">
              <label>프리뷰 이미지 URL</label>
              <input id="style-image-url" type="text" placeholder="https://... (선택 사항)">
            </div>
          </div>
          <div class="form-group">
            <label id="style-prompt-label">프롬프트 템플릿 *</label>
            <textarea id="style-prompt-template" rows="5" placeholder="스타일에 적용할 핵심 지시사항을 작성하세요."></textarea>
            <p class="info" id="style-prompt-help" style="margin-top:6px"></p>
          </div>
          <div class="form-group" id="style-image-instruction-group">
            <label>AI 추가 지시사항</label>
            <textarea id="style-gemini-instruction" rows="3" placeholder="예: 화면 안에 텍스트나 말풍선을 넣지 마세요."></textarea>
            <p class="info" style="margin-top:6px">이미지 프롬프트 생성 시 함께 적용되는 추가 제약입니다.</p>
          </div>
          <div style="display:flex;gap:8px;justify-content:flex-end">
            <button class="btn" id="style-cancel-btn" onclick="resetStyleForm()" style="display:none">수정 취소</button>
            <button class="btn btn-primary" id="style-save-btn" onclick="saveStylePreset()">스타일 저장</button>
          </div>
        </div>

        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px">
            <div class="card-title" style="margin:0">등록된 스타일</div>
            <div style="display:flex;gap:8px">
              <button class="btn btn-sm" data-style-filter="image" onclick="setStyleFilter('image')">이미지 스타일</button>
              <button class="btn btn-sm" data-style-filter="script" onclick="setStyleFilter('script')">대본 스타일</button>
              <button class="btn btn-sm" onclick="loadStylePresets()">새로고침</button>
            </div>
          </div>
          <div id="style-store-notice" class="info" style="margin-bottom:12px"></div>
          <div id="style-presets-list" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px"></div>
        </div>
      </div>

      <!-- ═══ Tab: Category Image Style Mapping ═══ -->
      <div class="tab-content" id="tab-category-image-styles">
        <div class="card">
          <div class="card-title">카테고리별 이미지 스타일 매칭</div>
          <p class="info" style="margin:-4px 0 16px">수동으로 선택한 스타일은 해당 카테고리의 자동 이미지 스타일 선택보다 우선합니다. 자동 선택으로 돌리면 제목과 주제에 맞춰 Worker가 선택합니다.</p>
          <table>
            <thead><tr><th>카테고리</th><th>자동 선택 기본값</th><th>수동 우선 스타일</th><th>저장</th></tr></thead>
            <tbody id="category-image-styles-body"></tbody>
          </table>
          <div class="empty" id="category-image-styles-empty" style="display:none">이미지 스타일 정보를 불러오지 못했습니다.</div>
        </div>
      </div>

      <!-- ═══ Tab: YouTube Explore ═══ -->
      <div class="tab-content" id="tab-yt-explore">
        <!-- 버블 차트 카드 -->
        <div class="card">
          <div class="card-title">&#x1F4C8; 트렌드 키워드 클라우드</div>
          <div class="yt-filter-row">
            <button class="btn btn-sm yt-lang-btn active" data-lang="ko">한국어</button>
            <button class="btn btn-sm yt-lang-btn" data-lang="en">English</button>
            <button class="btn btn-sm yt-lang-btn" data-lang="ja">日本語</button>
            <select id="yt-period">
              <option value="now">실시간</option>
              <option value="week">이번 주</option>
              <option value="month">이번 달</option>
            </select>
            <select id="yt-age">
              <option value="all">전체 연령</option>
              <option value="10s">10대</option>
              <option value="20s">20대</option>
              <option value="30s">30대</option>
              <option value="40s">40대 이상</option>
            </select>
            <button class="btn btn-sm btn-primary" onclick="loadTrendKeywords()">&#x1F504; 새로고침</button>
          </div>
          <div id="bubble-chart-container" style="height:420px;position:relative;">
            <div id="bubble-chart"></div>
            <div class="bubble-loading" id="bubble-loading" style="display:none">키워드 생성 중...</div>
          </div>
        </div>

        <!-- YouTube 검색 카드 -->
        <div class="card">
          <div class="card-title">&#x1F50D; YouTube 영상 검색</div>
          <div class="yt-search-row">
            <input type="text" id="yt-search-query" placeholder="검색어를 입력하세요..."
                   style="flex:1" onkeydown="if(event.key==='Enter')searchYtVideos()">
            <select id="yt-search-order">
              <option value="relevance">관련도</option>
              <option value="date">최신순</option>
              <option value="viewCount">조회수</option>
              <option value="rating">평점</option>
            </select>
            <select id="yt-search-period">
              <option value="">전체 기간</option>
              <option value="now">오늘</option>
              <option value="week">이번 주</option>
              <option value="month">이번 달</option>
            </select>
            <select id="yt-search-lang">
              <option value="">언어 없음</option>
              <option value="ko">한국어</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
            </select>
            <button class="btn btn-primary" onclick="searchYtVideos()">검색</button>
          </div>
          <div id="yt-suggested-tags" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;"></div>
        </div>

        <!-- 검색 결과 카드 -->
        <div class="card" id="yt-results-card" style="display:none">
          <div class="card-title">검색 결과 (<span id="yt-result-count">0</span>개)</div>
          <div style="overflow-x:auto">
            <table>
              <thead>
                <tr>
                  <th style="width:40px"></th>
                  <th style="width:120px">썸네일</th>
                  <th>제목</th>
                  <th style="width:140px">채널</th>
                  <th style="width:100px">게시일</th>
                  <th style="width:70px">조회수</th>
                  <th style="width:80px">구독자</th>
                  <th style="width:70px">기여도</th>
                  <th style="width:60px">성과</th>
                  <th style="width:60px">좋아요</th>
                  <th style="width:60px">작업</th>
                </tr>
              </thead>
              <tbody id="yt-results-body"></tbody>
            </table>
          </div>
          <div id="yt-search-loading" style="display:none;padding:20px;text-align:center;color:#8b949e">검색 중...</div>
        </div>
      </div>

      <!-- ═══ Tab: Hermes Autopilot ═══ -->
      <div class="tab-content" id="tab-hermes-autopilot">
        <div class="card">
          <div class="card-title">&#x1F916; Hermes 자동 대본 생성기 (Autopilot)</div>
          <p style="color:#8b949e;margin-bottom:16px;font-size:13px;">
            설정된 8가지 카테고리(탈북사연, 해외감동, 노후금융, 황혼19금, 옛날이야기, 한국사연, 무협, 경제)에 대해 
            유튜브 탐색 및 고성과 영상 분석 → 신규 주제 발굴 → 구조 기획 → 대본 생성을 자동으로 진행합니다.<br>
            생성된 대본 결과는 로컬 및 중앙 Supabase 서버(topics_queue)에 즉시 저장됩니다.
          </p>
          <div style="display:flex;gap:12px;align-items:center;margin-bottom:20px;">
            <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#8b949e;white-space:nowrap;">
              생성 수
              <input type="number" id="auto-start-limit" value="1" min="1" max="100" style="width:72px;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
            </label>
            <button class="btn btn-primary" id="auto-btn-start" onclick="startAutopilot()">▶ 자동 생성 시작</button>
            <button class="btn btn-danger" id="auto-btn-stop" onclick="stopAutopilot()" disabled>■ 자동 생성 중지</button>
            <span id="auto-status-text" class="badge badge-stopped">중지됨</span>
          </div>
          
          <div class="status-grid" style="grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:16px;">
            <div class="status-card">
              <div class="name">현재 상태</div>
              <table style="width:100%">
                <tr><th style="width:120px">동작 여부</th><td id="auto-info-running">-</td></tr>
                <tr><th>현재 단계</th><td id="auto-info-step">-</td></tr>
                <tr><th>진행 카테고리</th><td id="auto-info-category">-</td></tr>
                <tr><th>최근 생성 주제</th><td id="auto-info-topic">-</td></tr>
                <tr><th>선정 이미지 스타일</th><td id="auto-info-image-style">-</td></tr>
                <tr><th>세션 생성량</th><td id="auto-info-generated">0 개</td></tr>
              </table>
            </div>
            <div class="status-card">
              <div class="name" id="auto-active-category-title">설정된 카테고리 (8개)</div>
              <div id="auto-active-category-badges" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;"></div>
            </div>
          </div>
        </div>

        <!-- ⚙️ Autopilot Settings Panel -->
        <div class="card" style="margin-top:16px;">
          <div class="card-title">&#x2699;&#xFE0F; 오토파일럿 작업량 및 카테고리 세팅</div>
          <div class="status-grid" style="grid-template-columns: 1fr 1fr; gap:20px;">
            <div class="status-card" style="padding:16px;background:rgba(255,255,255,0.01);">
              <div class="name" style="margin-bottom:12px;">⏰ 작업 및 정지 규칙 설정</div>
              <div style="margin-bottom:12px;">
                <label style="display:block;font-size:12px;color:#8b949e;margin-bottom:6px;">작업 모드</label>
                <select id="auto-setting-mode" onchange="toggleLimitInput()" style="width:100%;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;">
                  <option value="infinite">무제한 지속 생성 🟢</option>
                  <option value="target_limit">목표 개수 생성 후 자동 정지 🟡</option>
                </select>
              </div>
              <div id="auto-limit-group" style="margin-bottom:12px;display:none;">
                <label style="display:block;font-size:12px;color:#8b949e;margin-bottom:6px;">목표 총 생성량 (개)</label>
                <input type="number" id="auto-setting-limit" value="10" min="1" style="width:100%;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
              </div>
              <div style="margin-bottom:12px;">
                <label style="display:block;font-size:12px;color:#8b949e;margin-bottom:6px;">카테고리별 최소 대기 대본 유지량 (버퍼)</label>
                <input type="number" id="auto-setting-buffer" value="5" min="1" style="width:100%;padding:8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1);color:#fff;border-radius:6px;outline:none;" />
                <p style="font-size:10px;color:#6e7681;margin-top:4px;line-height:1.4;">* 큐에 사전 대본이 이 수치 이상 존재 시 해당 카테고리는 건너뜁니다.</p>
              </div>
              <button class="btn btn-secondary" onclick="saveAutopilotSettings()" style="width:100%;margin-top:8px;">💾 설정값 저장</button>
            </div>
            
            <div class="status-card" style="padding:16px;background:rgba(255,255,255,0.01);">
              <div class="name" style="margin-bottom:12px;">🎛️ 생성할 카테고리 필터</div>
              <p style="font-size:11px;color:#8b949e;margin-bottom:8px;">체크한 카테고리만 자동 생성에 포함됩니다.</p>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;" id="auto-categories-checkboxes">
                <!-- Javascript will render checkboxes -->
              </div>
            </div>
          </div>
        </div>
        
        <div class="card">
          <div class="card-title">자동 생성 로그</div>
          <div class="log-viewer" id="auto-logs" style="height: 350px;">자동 생성기 로그가 여기에 표시됩니다...</div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- Job Detail Modal -->
<div class="modal-overlay" id="job-modal">
  <div class="modal">
    <span class="close" onclick="closeModal()">&times;</span>
    <h3 id="modal-title">작업 상세</h3>
    <div id="modal-body"></div>
  </div>
</div>

<!-- Toast Container -->
<div class="toast-container" id="toast-container"></div>

<script>
/* ── Globals ── */
let refreshInterval = null;
let countdown = 3;

/* ── API helpers ── */
async function api(method, path, body) {
  const opts = { method, headers: {'Content-Type': 'application/json'} };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 401) { window.location.href = '/login'; return null; }
  return res.json();
}

function showToast(msg, type='success') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

/* ── Tab switching ── */
const tabTitles = {
  'overview': '대시보드',
  'rendering': '렌더링 상황',
  'topic-search': '주제 찾기',
  'yt-explore': 'YouTube 탐색',
  'hermes-autopilot': 'Hermes 자동 생성',
  'hermes-gen': 'Hermes 주제 생성',
  'styles': '스타일 관리',
  'category-image-styles': '카테고리 이미지 스타일',
  'history': '작업 히스토리',
  'logs': '로그',
  'settings': '설정',
};

function switchTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + tabId).classList.add('active');
  document.querySelector(`.nav-item[data-tab="${tabId}"]`).classList.add('active');
  document.getElementById('page-title').textContent = tabTitles[tabId] || tabId;
  if (tabId === 'history') loadHistory();
  if (tabId === 'logs') loadLogs();
  if (tabId === 'rendering') loadRenderTab();
  if (tabId === 'settings') loadSettings();
  if (tabId === 'styles') loadStylePresets();
  if (tabId === 'category-image-styles') loadCategoryImageStyles();
  if (tabId === 'yt-explore') initYtExplore();
  if (tabId === 'hermes-autopilot') loadAutopilotStatus();
}

/* ── Time formatting ── */
function fmtTime(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleString('ko-KR');
}
function fmtShort(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('ko-KR');
}

/* ── Status badge ── */
const STATUS_LABELS = {
  QUEUED: '대기 중', CLAIMED: '작업 준비', PREPARING: '준비 중',
  RENDERING: '처리 중', UPLOADING: '결과 저장 중', COMPLETED: '완료',
  FAILED: '실패', CANCELED: '취소됨', ABANDONED: '중단됨',
  running: '실행 중', idle: '대기 중', stopped: '중지됨',
  starting: '시작 중', disabled: '사용 안 함',
};
const JOB_TYPE_LABELS = {
  render_video: '영상 렌더링',
  topic_research: '주제 탐색',
  topic_benchmark_analyze: '고성과 영상 분석',
  web_research: 'Gemini 웹 자료 조사',
  script_plan_generate: '대본 기획 생성',
  script_generate: '대본 생성',
};
const JOB_TYPE_DESCRIPTIONS = {
  render_video: '대본과 미디어를 조합해 최종 영상을 만들고 있습니다.',
  topic_research: '키워드와 시청자 반응을 바탕으로 콘텐츠 주제를 찾고 있습니다.',
  topic_benchmark_analyze: 'YouTube 고성과 영상의 제목, 구성, 반응을 분석하고 있습니다.',
  web_research: 'Gemini가 기사·논문·공식 자료를 검색해 대본 근거와 출처를 정리하고 있습니다.',
  script_plan_generate: '제목을 바탕으로 훅, 전개, 결말을 포함한 대본 기획을 만들고 있습니다.',
  script_generate: '기획을 바탕으로 시청 흐름을 고려한 대본을 작성하고 검수하고 있습니다.',
};
function humanStatus(s) {
  return STATUS_LABELS[s] || STATUS_LABELS[String(s || '').toLowerCase()] || s || '-';
}
function humanJobType(type) {
  return JOB_TYPE_LABELS[type] || type || '-';
}
function jobDescription(job) {
  return JOB_TYPE_DESCRIPTIONS[job?.job_type] || '작업 정보를 처리하고 있습니다.';
}
function displayProgress(job) {
  if (String(job?.status || '').toUpperCase() === 'COMPLETED') return 100;
  const value = Number(job?.progress || 0);
  return Math.max(0, Math.min(100, value));
}
function statusBadge(s) {
  if (!s) return '<span class="badge badge-idle">-</span>';
  return `<span class="badge badge-${String(s).toLowerCase()}">${humanStatus(s)}</span>`;
}

/* ── Process cards ── */
function renderProcessCards(status, jobs = []) {
  const el = document.getElementById('process-cards');
  const procs = status.processes || {};
  let html = '';
  for (const [name, info] of Object.entries(procs)) {
    const s = info.status || 'stopped';
    const label = {render_worker:'영상 작업 Worker', hermes_worker:'AI 기획·대본 Worker', local_api:'앱 연결 API', updater:'업데이트 도구'}[name] || name;
    const icon = {render_worker:'\u{1F3AC}', hermes_worker:'\u{1F4E6}', local_api:'\u{1F310}', updater:'\u{1F504}'}[name] || '\u{1F4BB}';
    const progress = Math.max(0, Math.min(100, Number(info.progress || 0)));
    const currentJobId = typeof info.current_job === 'string'
      ? info.current_job
      : (info.current_job?.job_id || info.current_job?.id || '');
    const activeJob = jobs.find(job => job.job_id === currentJobId);
    const currentJob = activeJob
      ? `${humanJobType(activeJob.job_type)} - ${jobDescription(activeJob)}`
      : (currentJobId ? `작업 처리 중 (${truncate(currentJobId, 8)})` : '진행 중인 작업 없음');
    const workerDescription = {
      render_worker: '영상 조립, 렌더링, 결과 파일 저장을 담당합니다.',
      hermes_worker: '주제 탐색, 고성과 분석, 대본 기획과 대본 생성을 담당합니다.',
      local_api: 'AIR Studio 앱과 Worker 사이의 요청을 연결합니다.',
      updater: 'Worker 업데이트를 확인하고 적용합니다.',
    }[name] || '';
    const hasError = info.last_error && info.last_error.length > 0;
    const isRecentError = hasError && (!info.last_success_at || info.last_success_at < (Date.now()/1000 - 300));
    const autoStart = (name === 'render_worker' || name === 'local_api');
    const displayLabel = name === 'remote_drive_worker' ? 'Drive API Render Worker' : label;
    const displayIcon = name === 'remote_drive_worker' ? '\u{2601}' : icon;

    html += `<div class="status-card">
      <div class="name">${displayIcon} ${displayLabel} ${statusBadge(s)}</div>
      <div class="info">${currentJob}</div>
      ${workerDescription ? `<div class="info" style="margin-top:4px">${workerDescription}</div>` : ''}
      <div class="info" style="margin-top:4px">프로세스 번호: ${info.pid || '-'}</div>
      ${progress > 0 ? `<div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>` : ''}
      ${hasError ? `<div class="info" style="color:${isRecentError ? '#f85149' : '#8b949e'};margin-top:4px">${isRecentError ? '\u{26A0} 오류: ' : '\u{2139} 이전 오류 (복구됨): '}${escapeHtml(info.last_error)}</div>` : ''}
      ${autoStart ? `<div class="info" style="color:#8b949e;margin-top:6px;font-size:12px">\u2705 프로그램 시작 시 자동 실행</div>` : name === 'hermes_worker' ? `
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
        <input id="hermes-start-limit" type="number" value="1" min="1" max="100" aria-label="생성할 영상 수" title="생성할 영상 수" style="width:64px;padding:6px 8px;background:rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.16);color:#fff;border-radius:6px;outline:none" />
        <button class="btn btn-sm btn-start" onclick="startHermesForLimit()" ${(s==='running'||s==='idle') ? 'disabled' : ''}>\u25B6 시작</button>
        <button class="btn btn-sm btn-stop" onclick="stopHermesGeneration()" ${s==='stopped' ? 'disabled' : ''}>\u23F9 중지</button>
      </div>
      <div class="info" style="color:#8b949e;margin-top:5px;font-size:12px">영상 수: 1개 = 벤치마크·기획·대본의 내부 3단계를 완료한 영상 1개입니다.</div>` : `
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-sm btn-start" onclick="startProcess('${name}')" ${(s==='running'||s==='idle') ? 'disabled' : ''}>\u25B6 시작</button>
        <button class="btn btn-sm btn-stop" onclick="stopProcess('${name}')" ${s==='stopped' ? 'disabled' : ''}>\u23F9 중지</button>
      </div>`}
    </div>`;
  }
  if (status.manager_alive === false) {
    html += `<div class="status-card" style="border-color:#f85149"><div class="name" style="color:#f85149">&#x26A0; Manager 오프라인</div><div class="info">heartbeat 없음 — Worker가 실행 중이 아닐 수 있습니다</div></div>`;
  }
  el.innerHTML = html;
}

/* ── Recent jobs ── */
function renderRecentJobs(jobs) {
  const el = document.getElementById('recent-jobs-body');
  const empty = document.getElementById('recent-empty');
  if (!jobs.length) { el.innerHTML = ''; empty.style.display = 'block'; return; }
  empty.style.display = 'none';
  el.innerHTML = jobs.slice(0, 10).map(j => `<tr>
    <td><a href="#" onclick="showJobDetail('${j.job_id}');return false">${j.job_id.substring(0,8)}</a></td>
    <td><strong>${humanJobType(j.job_type)}</strong><br><span class="info">${jobDescription(j)}</span></td>
    <td>${statusBadge(j.status)}</td>
    <td>${displayProgress(j)}%</td>
    <td>${fmtTime(j.created_at)}</td>
  </tr>`).join('');
}

/* ── Render tab ── */
function loadRenderTab() {
  api('GET', '/api/jobs?job_type=render_video&limit=20').then(data => {
    if (!data) return;
    const jobs = data.jobs || [];
    const el = document.getElementById('render-jobs-body');
    const empty = document.getElementById('render-empty');
    if (!jobs.length) { el.innerHTML = ''; empty.style.display = 'block'; return; }
    empty.style.display = 'none';
    el.innerHTML = jobs.map(j => `<tr>
      <td><a href="#" onclick="showJobDetail('${j.job_id}');return false">${j.job_id.substring(0,8)}</a></td>
      <td>${statusBadge(j.status)}</td>
      <td>${displayProgress(j)}%</td>
      <td>${escapeHtml(j.progress_message || j.error_message || '-')}</td>
      <td>${fmtShort(j.started_at)}</td>
      <td>${canCancel(j.status) ? `<button class="btn btn-danger btn-sm" onclick="cancelJob('${j.job_id}')">취소</button>` : ''}</td>
    </tr>`).join('');

    // Show active render
    const active = jobs.find(j => ['CLAIMED','PREPARING','RENDERING','UPLOADING'].includes(j.status));
    const acEl = document.getElementById('render-active-content');
    if (active) {
      acEl.innerHTML = `<div class="status-card">
        <div class="name">${statusBadge(active.status)} ${active.job_id.substring(0,8)}</div>
        <div class="info">${escapeHtml(active.progress_message || jobDescription(active))}</div>
        <div class="progress-bar"><div class="progress-fill" style="width:${displayProgress(active)}%"></div></div>
        <div style="margin-top:8px">${canCancel(active.status) ? `<button class="btn btn-danger btn-sm" onclick="cancelJob('${active.job_id}')">렌더 취소</button>` : ''}</div>
      </div>`;
    } else {
      acEl.innerHTML = '<div class="empty" style="padding:20px"><div class="icon">&#x274C;</div>활성 렌더 작업 없음</div>';
    }
  });
}

/* ── History tab ── */
function loadHistory() {
  const status = document.getElementById('hist-filter-status').value;
  const type = document.getElementById('hist-filter-type').value;
  let url = '/api/jobs?limit=100';
  if (status) url += `&status=${status}`;
  api('GET', url).then(data => {
    if (!data) return;
    let jobs = data.jobs || [];
    if (type) jobs = jobs.filter(j => j.job_type === type);
    const el = document.getElementById('history-body');
    const empty = document.getElementById('history-empty');
    if (!jobs.length) { el.innerHTML = ''; empty.style.display = 'block'; return; }
    empty.style.display = 'none';
    el.innerHTML = jobs.map(j => `<tr>
      <td><a href="#" onclick="showJobDetail('${j.job_id}');return false">${j.job_id.substring(0,8)}</a></td>
      <td><strong>${humanJobType(j.job_type)}</strong><br><span class="info">${jobDescription(j)}</span></td>
      <td>${statusBadge(j.status)}</td>
      <td>${displayProgress(j)}%</td>
      <td>${fmtTime(j.created_at)}</td>
      <td>${canCancel(j.status) ? `<button class="btn btn-danger btn-sm" onclick="cancelJob('${j.job_id}')">취소</button>` : `<button class="btn btn-sm" onclick="showJobDetail('${j.job_id}')">상세</button>`}</td>
    </tr>`).join('');
  });
}

/* ── Logs tab ── */
function loadLogs() {
  const proc = document.getElementById('log-process').value;
  api('GET', `/api/logs?process=${proc}&tail_lines=200`).then(data => {
    if (!data || data.error) {
      document.getElementById('log-output').textContent = data?.error || '로그를 불러올 수 없습니다';
      return;
    }
    document.getElementById('log-output').textContent = (data.lines || []).join('\n') || '(로그 없음)';
    document.getElementById('log-output').scrollTop = document.getElementById('log-output').scrollHeight;
  });
}

/* ── Shared style presets ── */
let stylePresets = [];
let styleFilter = 'image';

function updateStyleFormHelp() {
  const type = document.getElementById('style-preset-type').value;
  const isScript = type === 'script';
  document.getElementById('style-prompt-label').textContent = isScript ? '대본 작성 지시사항 *' : '이미지 프롬프트 템플릿 *';
  document.getElementById('style-prompt-template').placeholder = isScript
    ? '예: 1인칭 회고체로 시작하고, 대화는 짧게 사용하며, 장면마다 감정의 변화가 드러나게 작성하세요.'
    : '예: [SUBJECT], cinematic lighting, realistic textures, no text in image';
  document.getElementById('style-prompt-help').textContent = isScript
    ? '이 내용은 AI Worker의 대본 기획과 장면별 대본 생성 프롬프트에 그대로 들어갑니다.'
    : '이미지 프롬프트를 만들 때 스타일 접두어로 사용됩니다. 이미지·영상 프롬프트 생성 이관 단계에서 Worker가 직접 사용합니다.';
  document.getElementById('style-image-instruction-group').style.display = isScript ? 'none' : 'block';
}

function resetStyleForm() {
  document.getElementById('style-edit-key').value = '';
  document.getElementById('style-preset-type').value = 'image';
  document.getElementById('style-preset-type').disabled = false;
  document.getElementById('style-key-code').value = '';
  document.getElementById('style-key-code').readOnly = false;
  document.getElementById('style-name-ko').value = '';
  document.getElementById('style-name-vi').value = '';
  document.getElementById('style-image-url').value = '';
  document.getElementById('style-prompt-template').value = '';
  document.getElementById('style-gemini-instruction').value = '';
  document.getElementById('style-save-btn').textContent = '스타일 저장';
  document.getElementById('style-cancel-btn').style.display = 'none';
  updateStyleFormHelp();
}

function setStyleFilter(filter) {
  styleFilter = filter;
  document.querySelectorAll('[data-style-filter]').forEach(el => {
    el.classList.toggle('btn-primary', el.dataset.styleFilter === filter);
  });
  renderStylePresets();
}

function syncScriptStyleSelects() {
  const scriptStyles = stylePresets.filter(p => p.preset_type === 'script');
  for (const id of ['sp-style', 'sg-style']) {
    const select = document.getElementById(id);
    if (!select) continue;
    const selected = select.value || 'default';
    const options = [{key_code:'default', display_name_ko:'기본'}]
      .concat(scriptStyles.filter(p => p.key_code !== 'default'));
    select.innerHTML = options.map(p => `<option value="${escapeHtml(p.key_code)}">${escapeHtml(p.display_name_ko)} (${escapeHtml(p.key_code)})</option>`).join('');
    select.value = options.some(p => p.key_code === selected) ? selected : 'default';
  }
}

async function loadStylePresets() {
  const list = document.getElementById('style-presets-list');
  if (list) list.innerHTML = '<div class="info">스타일 목록을 불러오는 중...</div>';
  const data = await api('GET', '/api/style-presets');
  if (!data || data.error) {
    if (list) list.innerHTML = `<div class="info" style="color:#f85149">스타일 목록을 불러오지 못했습니다: ${escapeHtml(data?.error || '')}</div>`;
    return;
  }
  stylePresets = Array.isArray(data.presets) ? data.presets : [];
  document.getElementById('style-store-notice').textContent = data.shared_store_available
    ? '중앙 스타일 저장소와 연결됨. 저장 즉시 Worker의 생성 지침에도 반영됩니다.'
    : '중앙 스타일 저장소 연결이 없습니다. Worker 설정을 확인하세요.';
  syncScriptStyleSelects();
  renderStylePresets();
}

function renderStylePresets() {
  const list = document.getElementById('style-presets-list');
  if (!list) return;
  const presets = stylePresets.filter(p => p.preset_type === styleFilter);
  if (!presets.length) {
    list.innerHTML = '<div class="empty" style="padding:20px">등록된 스타일이 없습니다.</div>';
    return;
  }
  list.innerHTML = presets.map(p => `<div class="status-card" style="display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
      <div><strong>${escapeHtml(p.display_name_ko || p.key_code)}</strong>${p.display_name_vi ? `<div class="info">${escapeHtml(p.display_name_vi)}</div>` : ''}<div class="info">코드: ${escapeHtml(p.key_code)}</div></div>
      <div style="display:flex;gap:4px"><button class="btn btn-sm" onclick="editStylePreset('${escapeHtml(p.key_code)}')">수정</button><button class="btn btn-danger btn-sm" onclick="deleteStylePreset('${escapeHtml(p.preset_type)}','${escapeHtml(p.key_code)}')">삭제</button></div>
    </div>
    ${p.image_url ? `<img src="${escapeHtml(p.image_url)}" alt="" style="width:72px;height:72px;object-fit:cover;border-radius:6px;border:1px solid #30363d">` : ''}
    <div class="result-viewer" style="max-height:110px">${escapeHtml(p.prompt_template || '')}</div>
    ${p.gemini_instruction ? `<div class="info">추가 지시: ${escapeHtml(p.gemini_instruction)}</div>` : ''}
  </div>`).join('');
}

let categoryImageStyleCatalog = [];

async function loadCategoryImageStyles() {
  const body = document.getElementById('category-image-styles-body');
  const empty = document.getElementById('category-image-styles-empty');
  if (!body || !empty) return;
  body.innerHTML = '<tr><td colspan="4" class="info">카테고리와 이미지 스타일을 불러오는 중...</td></tr>';
  empty.style.display = 'none';
  const data = await api('GET', '/api/category-image-style-mappings');
  if (!data || data.error || !Array.isArray(data.categories) || !Array.isArray(data.styles)) {
    body.innerHTML = '';
    empty.textContent = `이미지 스타일 정보를 불러오지 못했습니다. ${data?.error || ''}`;
    empty.style.display = 'block';
    return;
  }
  categoryImageStyleCatalog = data.styles;
  if (!categoryImageStyleCatalog.length) {
    body.innerHTML = '';
    empty.textContent = '등록된 이미지 스타일이 없습니다. 먼저 스타일 관리에서 이미지 스타일을 등록하세요.';
    empty.style.display = 'block';
    return;
  }
  body.innerHTML = data.categories.map((item, index) => {
    const selectId = `category-image-style-${index}`;
    const automatic = escapeHtml(item.automatic_default || 'realistic');
    const options = [
      `<option value="">자동 선택 (${automatic})</option>`,
      ...categoryImageStyleCatalog.map(style => {
        const key = String(style.key_code || '');
        const label = `${style.display_name_ko || key} (${key})`;
        return `<option value="${escapeHtml(key)}" ${item.manual_override === key ? 'selected' : ''}>${escapeHtml(label)}</option>`;
      }),
    ].join('');
    return `<tr>
      <td><strong>${escapeHtml(item.name)}</strong></td>
      <td><code>${automatic}</code></td>
      <td><select id="${selectId}">${options}</select></td>
      <td><button class="btn btn-sm btn-primary" onclick="saveCategoryImageStyle('${escapeHtml(item.name)}', '${selectId}')">저장</button></td>
    </tr>`;
  }).join('');
}

async function saveCategoryImageStyle(category, selectId) {
  const select = document.getElementById(selectId);
  if (!select) return;
  select.disabled = true;
  try {
    const result = await api('PUT', `/api/category-image-style-mappings/${encodeURIComponent(category)}`, {
      image_style: select.value,
    });
    if (!result?.success) {
      showToast('카테고리 이미지 스타일 저장 실패: ' + (result?.error || '응답 없음'), 'error');
      return;
    }
    showToast(select.value ? `${category}: ${select.value} 수동 우선 적용` : `${category}: 자동 선택으로 전환`);
    await loadCategoryImageStyles();
  } catch (e) {
    showToast('카테고리 이미지 스타일 저장 통신 실패', 'error');
  } finally {
    select.disabled = false;
  }
}

function editStylePreset(key) {
  const preset = stylePresets.find(p => p.key_code === key);
  if (!preset) return;
  document.getElementById('style-edit-key').value = preset.key_code;
  document.getElementById('style-preset-type').value = preset.preset_type;
  document.getElementById('style-preset-type').disabled = true;
  document.getElementById('style-key-code').value = preset.key_code;
  document.getElementById('style-key-code').readOnly = true;
  document.getElementById('style-name-ko').value = preset.display_name_ko || '';
  document.getElementById('style-name-vi').value = preset.display_name_vi || '';
  document.getElementById('style-image-url').value = preset.image_url || '';
  document.getElementById('style-prompt-template').value = preset.prompt_template || '';
  document.getElementById('style-gemini-instruction').value = preset.gemini_instruction || '';
  document.getElementById('style-save-btn').textContent = '스타일 수정 저장';
  document.getElementById('style-cancel-btn').style.display = 'inline-flex';
  updateStyleFormHelp();
  document.getElementById('style-key-code').scrollIntoView({behavior:'smooth', block:'center'});
}

async function saveStylePreset() {
  const body = {
    preset_type: document.getElementById('style-preset-type').value,
    key_code: document.getElementById('style-key-code').value.trim(),
    display_name_ko: document.getElementById('style-name-ko').value.trim(),
    display_name_vi: document.getElementById('style-name-vi').value.trim(),
    image_url: document.getElementById('style-image-url').value.trim(),
    prompt_template: document.getElementById('style-prompt-template').value.trim(),
    gemini_instruction: document.getElementById('style-gemini-instruction').value.trim(),
  };
  if (!body.key_code || !body.display_name_ko || !body.prompt_template) {
    showToast('스타일 코드, 한글 표시명, 지시사항을 입력하세요.', 'error'); return;
  }
  const button = document.getElementById('style-save-btn');
  button.disabled = true;
  try {
    const data = await api('POST', '/api/style-presets', body);
    if (!data || data.detail || data.error) throw new Error(data?.detail || data?.error || '저장 실패');
    showToast('스타일을 저장했고 Worker 생성 지침에 반영했습니다.');
    resetStyleForm();
    await loadStylePresets();
  } catch (e) {
    showToast(`스타일 저장 실패: ${e.message || e}`, 'error');
  } finally {
    button.disabled = false;
  }
}

async function deleteStylePreset(type, key) {
  if (!confirm(`'${key}' 스타일을 삭제하시겠습니까? 이미 이 스타일을 선택한 카테고리는 기본 스타일로 처리됩니다.`)) return;
  const data = await api('DELETE', `/api/style-presets/${encodeURIComponent(type)}/${encodeURIComponent(key)}`);
  if (!data || data.detail || data.error) { showToast(`스타일 삭제 실패: ${data?.detail || data?.error || ''}`, 'error'); return; }
  showToast('스타일을 삭제했습니다.');
  resetStyleForm();
  await loadStylePresets();
}

/* ── Job detail modal ── */
async function showJobDetail(jobId) {
  const data = await api('GET', `/api/jobs/${jobId}`);
  if (!data) return;
  const el = document.getElementById('modal-body');
  document.getElementById('modal-title').textContent = `작업 상세: ${jobId.substring(0,12)}`;

  let html = `<table style="width:100%">
    <tr><th>ID</th><td>${data.job_id}</td></tr>
    <tr><th>작업</th><td><strong>${humanJobType(data.job_type)}</strong><br><span class="info">${jobDescription(data)}</span></td></tr>
    <tr><th>상태</th><td>${statusBadge(data.status)}</td></tr>
    <tr><th>진행률</th><td>${displayProgress(data)}% — ${escapeHtml(data.progress_message || (data.status === 'COMPLETED' ? '작업 완료' : ''))}</td></tr>
    <tr><th>요청 위치</th><td>${escapeHtml(data.source || '-')}</td></tr>
    <tr><th>생성</th><td>${fmtTime(data.created_at)}</td></tr>
    <tr><th>시작</th><td>${fmtTime(data.started_at)}</td></tr>
    <tr><th>완료</th><td>${fmtTime(data.completed_at)}</td></tr>
    ${data.error_message ? `<tr><th>오류</th><td style="color:#f85149">${escapeHtml(data.error_message)}</td></tr>` : ''}
    ${data.output_path ? `<tr><th>출력</th><td>${escapeHtml(data.output_path)}</td></tr>` : ''}
  </table>`;

  // Payload
  if (data.payload && Object.keys(data.payload).length) {
    html += `<div class="card" style="margin-top:16px"><div class="card-title">작업 입력값</div><div class="result-viewer">${escapeHtml(JSON.stringify(data.payload, null, 2))}</div></div>`;
  }

  // Transitions timeline
  if (data.transitions && data.transitions.length) {
    html += `<div class="card" style="margin-top:16px"><div class="card-title">상태 전이</div><div class="timeline">`;
    for (const t of data.transitions) {
      html += `<div class="timeline-item">${statusBadge(t.to_status)} <span class="time">${fmtTime(t.at)}</span>${t.reason ? ` — ${escapeHtml(t.reason)}` : ''}</div>`;
    }
    html += `</div></div>`;
  }

  // Result
  if (data.result) {
    const resultText = JSON.stringify(data.result, null, 2);
    html += `<div class="card" style="margin-top:16px"><div class="card-title">결과</div><div class="result-viewer">${escapeHtml(resultText)}</div></div>`;
  }

  html += `<div style="margin-top:16px">${canCancel(data.status) ? `<button class="btn btn-danger" onclick="cancelJob('${jobId}');closeModal()">작업 취소</button>` : ''}</div>`;

  el.innerHTML = html;
  document.getElementById('job-modal').classList.add('active');
}

function closeModal() {
  document.getElementById('job-modal').classList.remove('active');
}

/* ── Submit: topic_research ── */
async function submitTopicResearch() {
  const keyword = document.getElementById('tr-keyword').value.trim();
  if (!keyword) { showToast('키워드를 입력하세요', 'error'); return; }
  const payload = {
    keyword,
    language: document.getElementById('tr-language').value,
    country: document.getElementById('tr-country').value.trim() || 'global',
    count: parseInt(document.getElementById('tr-count').value) || 10,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'topic_research', payload });
  if (res && res.job_id) {
    showToast(`주제 찾기 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Submit: topic_benchmark_analyze ── */
async function submitBenchmark() {
  const keyword = document.getElementById('ba-keyword').value.trim();
  if (!keyword) { showToast('키워드를 입력하세요', 'error'); return; }
  const payload = {
    keyword,
    language: document.getElementById('ba-language').value,
    video_type: document.getElementById('ba-video-type').value,
    max_candidates: parseInt(document.getElementById('ba-max-candidates').value) || 1,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'topic_benchmark_analyze', payload });
  if (res && res.job_id) {
    showToast(`벤치마크 분석 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Submit: script_plan_generate ── */
async function submitScriptPlan() {
  const topic = document.getElementById('sp-topic').value.trim();
  if (!topic) { showToast('주제를 입력하세요', 'error'); return; }
  const payload = {
    topic_queue_id: 'dashboard-' + Date.now(),
    topic,
    target_duration_seconds: parseInt(document.getElementById('sp-duration').value) || 600,
    script_style: document.getElementById('sp-style').value,
    language: document.getElementById('sp-language').value,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'script_plan_generate', payload });
  if (res && res.job_id) {
    showToast(`구조 생성 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Submit: script_generate ── */
async function submitScriptGenerate() {
  const topic = document.getElementById('sg-topic').value.trim();
  if (!topic) { showToast('주제를 입력하세요', 'error'); return; }
  let structure = undefined;
  const structText = document.getElementById('sg-structure').value.trim();
  if (structText) {
    try { structure = JSON.parse(structText); }
    catch(e) { showToast('구조 JSON 파싱 오류', 'error'); return; }
  }
  const payload = {
    topic_queue_id: 'dashboard-' + Date.now(),
    topic,
    structure: structure || null,
    target_duration_seconds: parseInt(document.getElementById('sg-duration').value) || 600,
    script_style: document.getElementById('sg-style').value,
    language: 'ko',
    narration_mode: document.getElementById('sg-narration-mode').value,
  };
  const res = await api('POST', '/api/jobs/submit', { job_type: 'script_generate', payload });
  if (res && res.job_id) {
    showToast(`대본 생성 작업이 제출되었습니다: ${res.job_id.substring(0,8)}`);
    switchTab('history');
  } else {
    showToast('작업 제출 실패', 'error');
  }
}

/* ── Cancel job ── */
async function cancelJob(jobId) {
  const res = await api('POST', `/api/jobs/${jobId}/cancel`);
  if (res && res.success !== false) {
    showToast(`작업 ${jobId.substring(0,8)} 취소됨`);
    refreshAll();
  } else {
    showToast(`취소 실패: ${res?.error || '알 수 없음'}`, 'error');
  }
}

/* ── Cancel helper ── */
function canCancel(status) {
  return ['QUEUED','CLAIMED','PREPARING','RENDERING','UPLOADING'].includes(status);
}

/* ── Process start / stop ── */
const PROCESS_API_NAME = { hermes_worker: 'hermes', render_worker: 'render', remote_drive_worker: 'remote-drive' };

async function startProcess(name) {
  try {
    const apiName = PROCESS_API_NAME[name] || name;
    const res = await api('POST', `/api/processes/${apiName}/start`);
    showToast(`${{hermes_worker:'AI 기획·대본 Worker', render_worker:'영상 작업 Worker'}[name] || name} 시작을 요청했습니다.`, 'info');
    setTimeout(refreshAll, 1500);
  } catch(e) {
    showToast(`시작 실패: ${e}`, 'error');
  }
}

async function startHermesForLimit() {
  const input = document.getElementById('hermes-start-limit');
  const targetLimit = Number.parseInt(input?.value, 10);
  if (!Number.isInteger(targetLimit) || targetLimit < 1 || targetLimit > 100) {
    showToast('생성 수는 1~100 사이로 입력하세요.', 'error');
    input?.focus();
    return;
  }

  try {
    const worker = await api('POST', '/api/processes/hermes/start');
    if (!worker?.success) {
      showToast('AI 기획·대본 Worker 시작 실패: ' + (worker?.error || '응답 없음'), 'error');
      return;
    }

    const autoStartInput = document.getElementById('auto-start-limit');
    if (autoStartInput) autoStartInput.value = String(targetLimit);
    const autopilot = await api('POST', '/api/autopilot/hermes/start', {
      settings: { mode: 'target_limit', target_limit: targetLimit },
    });
    if (!autopilot?.success) {
      showToast('자동 생성 시작 실패: ' + (autopilot?.error || '응답 없음'), 'error');
      return;
    }

    showToast(`AI Worker가 ${targetLimit}개 생성한 뒤 자동 생성을 멈춥니다.`, 'success');
    setTimeout(refreshAll, 1000);
  } catch (e) {
    showToast('AI Worker 시작 통신 실패', 'error');
  }
}

async function stopHermesGeneration() {
  try {
    const result = await api('POST', '/api/autopilot/hermes/stop');
    if (result?.success) {
      const cancelled = Number(result.cancelled_job_count || 0);
      showToast(`AI 기획·대본 Worker를 중지했습니다. 남은 자동 작업 ${cancelled}개도 취소했습니다.`, 'info');
    } else {
      showToast('AI 기획·대본 Worker 중지 실패: ' + (result?.error || '응답 없음'), 'error');
    }
    setTimeout(refreshAll, 1000);
  } catch (e) {
    showToast('AI Worker 중지 통신 실패', 'error');
  }
}

async function stopProcess(name) {
  try {
    const apiName = PROCESS_API_NAME[name] || name;
    const res = await api('POST', `/api/processes/${apiName}/stop`);
    showToast(`${{hermes_worker:'AI 기획·대본 Worker', render_worker:'영상 작업 Worker'}[name] || name} 중지를 요청했습니다.`, 'info');
    setTimeout(refreshAll, 1500);
  } catch(e) {
    showToast(`중지 실패: ${e}`, 'error');
  }
}

/* ── Utility ── */
function truncate(s, n) { return s && s.length > n ? s.substring(0, n) + '...' : (s || ''); }
function escapeHtml(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

/* ── Refresh all ── */
async function refreshAll() {
  countdown = 3;
  try {
    const jobs = await api('GET', '/api/jobs?limit=10');
    const status = await api('GET', '/api/status');
    if (!status) return;
    const recentJobs = jobs?.jobs || [];
    renderProcessCards(status, recentJobs);
    renderRecentJobs(recentJobs);

    // Refresh active tab-specific data
    const activeTab = document.querySelector('.nav-item.active')?.dataset.tab;
    if (activeTab === 'rendering') loadRenderTab();
    if (activeTab === 'history') loadHistory();
    if (activeTab === 'hermes-autopilot') loadAutopilotStatus();
  } catch(e) { /* silent */ }
}

/* ── Auto-refresh countdown ── */
setInterval(() => {
  countdown--;
  if (countdown <= 0) { countdown = 3; refreshAll(); }
  document.getElementById('refresh-timer').textContent = `${countdown}s 후 새로고침`;
}, 1000);

/* ── Logout ── */
async function doLogout() {
  await fetch('/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}

/* ══════════════════════════════════════════════
   Settings Tab
   ══════════════════════════════════════════════ */

/* Setting label map for Korean UI */
const settingLabels = {
  'GEMINI_API_KEY': 'Gemini API Key',
  'CLAUDE_API_KEY': 'Claude API Key',
  'YOUTUBE_API_KEY': 'YouTube API Key',
  'ELEVENLABS_API_KEY': 'ElevenLabs API Key',
  'SUNO_API_KEY': 'Suno API Key',
  'TOPIC_GENERATION_MODEL': '주제 생성 모델',
  'SCRIPT_GENERATION_MODEL': '대본 생성 모델',
  'SCRIPT_PLANNING_MODEL': '구조 생성 모델',
};

/* Icons for API keys vs model settings */
const settingIcons = {
  'GEMINI_API_KEY': '&#x1F4E7;',
  'CLAUDE_API_KEY': '&#x1F4E7;',
  'YOUTUBE_API_KEY': '&#x1F3AC;',
  'ELEVENLABS_API_KEY': '&#x1F3A4;',
  'SUNO_API_KEY': '&#x1F3B5;',
  'TOPIC_GENERATION_MODEL': '&#x1F916;',
  'SCRIPT_GENERATION_MODEL': '&#x1F916;',
  'SCRIPT_PLANNING_MODEL': '&#x1F916;',
};

/* Track original values for dirty detection */
let settingsOriginal = {};

async function loadSettings() {
  const data = await api('GET', '/api/settings');
  if (!data) return;
  const list = data.settings || [];
  const container = document.getElementById('settings-list');
  settingsOriginal = {};

  let html = '';
  for (const item of list) {
    const label = settingLabels[item.key] || item.key;
    const icon = settingIcons[item.key] || '&#x2699;';
    const placeholder = item.value || '';
    const setLabel = item.set ? '<span style="color:#3fb950;font-size:12px;margin-left:8px">&#x2714; 설정됨</span>' : '<span style="color:#8b949e;font-size:12px;margin-left:8px">미설정</span>';
    html += `
      <div class="setting-row" style="display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #21262d;" data-key="${escapeHtml(item.key)}">
        <span style="font-size:18px;width:28px;text-align:center;">${icon}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:14px;margin-bottom:4px;">
            ${escapeHtml(label)} ${setLabel}
          </div>
          <input type="text" id="setting-${escapeHtml(item.key)}" class="setting-input"
            placeholder="${escapeHtml(placeholder)}"
            style="width:100%;padding:8px 12px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#e1e4e8;font-size:13px;font-family:monospace;outline:none;"
            onkeydown="if(event.key==='Enter'){event.preventDefault();saveSetting('${escapeHtml(item.key)}')}"
          />
        </div>
        <button class="btn btn-sm btn-primary" onclick="saveSetting('${escapeHtml(item.key)}')" style="white-space:nowrap;">저장</button>
      </div>`;
    settingsOriginal[item.key] = item.value;
  }
  container.innerHTML = html;
  document.getElementById('settings-status').textContent = '';
}

async function saveSetting(key) {
  const input = document.getElementById('setting-' + key);
  const value = input.value.trim();
  const statusEl = document.getElementById('settings-status');
  statusEl.textContent = '저장 중...';
  statusEl.style.color = '#8b949e';

  const res = await api('POST', '/api/settings', { key, value });
  if (res && res.success) {
    showToast(`${settingLabels[key] || key} 저장 완료`);
    statusEl.textContent = '';
    await loadSettings();
  } else {
    showToast(`저장 실패: ${res?.error || '알 수 없음'}`, 'error');
    statusEl.textContent = '저장 실패';
    statusEl.style.color = '#f85149';
  }
}

async function saveAllSettings() {
  const inputs = document.querySelectorAll('.setting-input');
  let savedCount = 0;
  let errorCount = 0;
  const statusEl = document.getElementById('settings-status');
  statusEl.textContent = '저장 중...';
  statusEl.style.color = '#8b949e';

  for (const input of inputs) {
    const key = input.id.replace('setting-', '');
    const value = input.value.trim();
    // Only save if the user actually typed something new (not just the placeholder hint)
    if (value === '') continue;
    const res = await api('POST', '/api/settings', { key, value });
    if (res && res.success) savedCount++;
    else errorCount++;
  }

  if (errorCount === 0 && savedCount > 0) {
    showToast(`${savedCount}개 설정 저장 완료`);
    statusEl.textContent = '';
    await loadSettings();
  } else if (savedCount > 0) {
    showToast(`${savedCount}개 저장 완료, ${errorCount}개 실패`, 'warning');
    statusEl.textContent = `${savedCount}개 성공, ${errorCount}개 실패`;
    statusEl.style.color = '#d29922';
    await loadSettings();
  } else {
    showToast('변경사항 없음', 'info');
    statusEl.textContent = '변경사항 없음';
    statusEl.style.color = '#8b949e';
  }
}

/* ── YouTube Explore ── */
let ytExploreInitialized = false;
const BUBBLE_COLORS = {
  'Entertainment': '#58a6ff', 'Gaming': '#3fb950', 'Music': '#a371f7',
  'Technology': '#d29922', 'Education': '#f85149', 'Sports': '#79c0ff',
  'News': '#ffa657', 'Lifestyle': '#ff7b72', 'Cooking': '#d2a8ff',
  'Travel': '#7ee787', 'Finance': '#f0883e', 'Health': '#56d364',
  'Science': '#bc8cff', 'Comedy': '#79c0ff', 'Film': '#db61a2',
};
const BUBBLE_FALLBACK = '#8b949e';

function initYtExplore() {
  if (ytExploreInitialized) return;
  ytExploreInitialized = true;
  document.querySelectorAll('.yt-lang-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.yt-lang-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadTrendKeywords();
    });
  });
  loadTrendKeywords();
}

async function loadTrendKeywords() {
  const lang = (document.querySelector('.yt-lang-btn.active') || {}).dataset?.lang || 'ko';
  const period = document.getElementById('yt-period').value;
  const age = document.getElementById('yt-age').value;
  const cacheKey = 'yt-trending-' + lang;
  const cached = localStorage.getItem(cacheKey);
  if (cached) {
    try { renderBubbleChart(JSON.parse(cached)); } catch(e) {}
  }
  document.getElementById('bubble-loading').style.display = 'flex';
  try {
    const data = await api('GET', '/api/yt/trending-keywords?language=' + lang + '&period=' + period + '&age=' + age);
    if (data && data.error) {
      document.getElementById('bubble-chart').innerHTML = '<div style="text-align:center;padding:80px;color:#f85149">⚠ ' + data.error + '</div>';
    } else if (data && data.keywords && data.keywords.length > 0) {
      localStorage.setItem(cacheKey, JSON.stringify(data.keywords));
      renderBubbleChart(data.keywords);
    } else if (!cached) {
      document.getElementById('bubble-chart').innerHTML = '<div style="text-align:center;padding:80px;color:#8b949e">키워드 생성 결과가 비어있습니다. 다시 시도해주세요.</div>';
    }
  } catch(e) {
    console.error('loadTrendKeywords error:', e);
    document.getElementById('bubble-chart').innerHTML = '<div style="text-align:center;padding:80px;color:#f85149">⚠ 네트워크 오류: ' + e.message + '</div>';
  } finally {
    document.getElementById('bubble-loading').style.display = 'none';
  }
}

function renderBubbleChart(keywords) {
  const container = document.getElementById('bubble-chart');
  const width = container.parentElement.clientWidth || 800;
  const height = 420;
  d3.select('#bubble-chart').selectAll('*').remove();
  const svg = d3.select('#bubble-chart').append('svg')
    .attr('width', width).attr('height', height);
  const g = svg.append('g');
  const data = keywords.map((k, i) => ({
    id: i, keyword: k.keyword || '', translation: k.translation || '',
    volume: Math.max(Number(k.volume) || 20, 15),
    category: k.category || 'Other'
  }));
  const sizeScale = d3.scaleLinear().domain([15, 100]).range([40, 120]);
  const nodes = data.map(d => ({
    ...d, w: sizeScale(d.volume), h: sizeScale(d.volume) * 0.55
  }));
  const simulation = d3.forceSimulation(nodes)
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('charge', d3.forceManyBody().strength(5))
    .force('collision', d3.forceCollide().radius(d => Math.max(d.w, d.h) / 2 + 4).iterations(3))
    .force('x', d3.forceX(width / 2).strength(0.05))
    .force('y', d3.forceY(height / 2).strength(0.05));
  const nodeGroup = g.selectAll('g.bubble-node')
    .data(nodes).enter().append('g')
    .attr('class', 'bubble-node').call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );
  nodeGroup.append('rect')
    .attr('rx', 8).attr('ry', 8)
    .attr('width', d => d.w).attr('height', d => d.h)
    .attr('x', d => -d.w / 2).attr('y', d => -d.h / 2)
    .attr('fill', d => (BUBBLE_COLORS[d.category] || BUBBLE_FALLBACK) + '22')
    .attr('stroke', d => BUBBLE_COLORS[d.category] || BUBBLE_FALLBACK)
    .attr('stroke-width', 1.5)
    .attr('cursor', 'pointer')
    .on('click', (e, d) => {
      document.getElementById('yt-search-query').value = d.keyword;
      searchYtVideos();
    });
  nodeGroup.append('text')
    .attr('text-anchor', 'middle').attr('dy', '-0.1em')
    .attr('fill', '#c9d1d9').attr('font-size', d => Math.max(10, Math.min(d.w * 0.15, 16)))
    .attr('font-weight', d => d.volume > 70 ? '700' : '400')
    .attr('pointer-events', 'none')
    .text(d => d.keyword.length > 12 ? d.keyword.slice(0, 11) + '…' : d.keyword);
  nodeGroup.append('text')
    .attr('text-anchor', 'middle').attr('dy', '1.2em')
    .attr('fill', '#8b949e').attr('font-size', d => Math.max(8, Math.min(d.w * 0.1, 12)))
    .attr('pointer-events', 'none')
    .text(d => d.volume);
  simulation.on('tick', () => {
    nodeGroup.attr('transform', d => 'translate(' + d.x + ',' + d.y + ')');
  });
}

async function searchYtVideos() {
  const query = document.getElementById('yt-search-query').value.trim();
  if (!query) return;
  const order = document.getElementById('yt-search-order').value;
  const period = document.getElementById('yt-search-period').value;
  const lang = document.getElementById('yt-search-lang').value;
  const body = { query, order, max_results: 12 };
  if (period) {
    const now = new Date();
    if (period === 'now') now.setDate(now.getDate() - 1);
    else if (period === 'week') now.setDate(now.getDate() - 7);
    else if (period === 'month') now.setMonth(now.getMonth() - 1);
    body.published_after = now.toISOString();
  }
  if (lang) body.relevance_language = lang;
  const loading = document.getElementById('yt-search-loading');
  const card = document.getElementById('yt-results-card');
  loading.style.display = 'block';
  card.style.display = 'block';
  document.getElementById('yt-results-body').innerHTML = '';
  document.getElementById('yt-result-count').textContent = '0';
  let searchError = null;
  try {
    const searchResult = await api('POST', '/api/yt/search', body);
    if (!searchResult || searchResult.error) {
      searchError = searchResult?.error || '검색 요청 실패';
      return;
    }
    const items = searchResult.items || [];
    if (items.length === 0) {
      searchError = 'EMPTY';
      return;
    }
    const videoIds = items.map(i => i.id.videoId).filter(Boolean).join(',');
    const channelIds = [...new Set(items.map(i => i.snippet.channelId).filter(Boolean))].join(',');
    const [videosRes, channelsRes] = await Promise.all([
      api('GET', '/api/yt/videos/' + videoIds),
      channelIds ? api('GET', '/api/yt/channel/' + channelIds) : Promise.resolve(null)
    ]);
    const videoMap = {};
    if (videosRes && videosRes.items) {
      videosRes.items.forEach(v => { videoMap[v.id] = v; });
    }
    const channelMap = {};
    if (channelsRes && channelsRes.items) {
      channelsRes.items.forEach(c => { channelMap[c.id] = c; });
    }
    const videos = items
      .filter(i => i.id && i.id.videoId && videoMap[i.id.videoId])
      .map(i => {
        const v = videoMap[i.id.videoId];
        const ch = channelMap[i.snippet.channelId] || {};
        const stats = v.statistics || {};
        const chStats = ch.statistics || {};
        const views = parseInt(stats.viewCount) || 0;
        const likes = parseInt(stats.likeCount) || 0;
        const subs = parseInt(chStats.subscriberCount) || 1;
        const chViews = parseInt(chStats.viewCount) || 0;
        const chCount = parseInt(chStats.videoCount) || 1;
        const chAvgViews = chViews / chCount;
        const contribution = chAvgViews > 0 ? ((views / chAvgViews) * 100) : 0;
        const performance = views / subs;
        return {
          videoId: v.id,
          title: v.snippet.title,
          thumbnail: (v.snippet.thumbnails || {}).high?.url || (v.snippet.thumbnails || {}).medium?.url || '',
          channelTitle: v.snippet.channelTitle,
          channelId: v.snippet.channelId,
          channelAvatar: (ch.snippet || {}).thumbnails?.default?.url || '',
          publishedAt: v.snippet.publishedAt,
          views, likes, subs, comments: parseInt(stats.commentCount) || 0,
          duration: (v.contentDetails || {}).duration || '',
          contribution: Math.round(contribution),
          performance: performance.toFixed(2),
          tags: (v.snippet || {}).tags || [],
        };
      });
    renderYtResults(videos);
    renderSuggestedTags(videos);
  } catch(e) {
    console.error('searchYtVideos error:', e);
    searchError = e.message || '네트워크 오류';
  } finally {
    loading.style.display = 'none';
    if (searchError) {
      document.getElementById('yt-results-body').innerHTML =
        '<tr><td colspan="11" style="text-align:center;padding:40px;color:#f85149">⚠ ' + searchError + '</td></tr>';
    }
  }
}

function renderYtResults(videos) {
  const tbody = document.getElementById('yt-results-body');
  document.getElementById('yt-result-count').textContent = videos.length;
  tbody.innerHTML = videos.map((v, i) => {
    const viralClass = v.contribution > 200 ? 'yt-viral-high' : v.contribution > 50 ? 'yt-viral-mid' : 'yt-viral-low';
    return '<tr>' +
      '<td style="text-align:center;color:#8b949e;font-size:12px">' + (i + 1) + '</td>' +
      '<td><img class="yt-thumb" src="' + escHtml(v.thumbnail) + '" loading="lazy" onerror="this.style.display=\'none\'"></td>' +
      '<td class="yt-title-cell" title="' + escHtml(v.title) + '">' +
        '<a href="https://youtube.com/watch?v=' + v.videoId + '" target="_blank" style="color:#c9d1d9;font-size:13px">' + escHtml(v.title) + '</a>' +
        '<div style="font-size:11px;color:#8b949e;margin-top:2px">' + parseDuration(v.duration) + '</div>' +
      '</td>' +
      '<td style="font-size:12px">' +
        '<img class="yt-channel-avatar" src="' + escHtml(v.channelAvatar) + '" onerror="this.style.display=\'none\'">' +
        escHtml(v.channelTitle) +
      '</td>' +
      '<td style="font-size:12px;color:#8b949e">' + formatDate(v.publishedAt) + '</td>' +
      '<td style="font-size:12px;text-align:right">' + formatNum(v.views) + '</td>' +
      '<td style="font-size:12px;text-align:right">' + formatNum(v.subs) + '</td>' +
      '<td style="text-align:center"><span class="yt-viral-score ' + viralClass + '">' + v.contribution + '%</span></td>' +
      '<td style="font-size:12px;text-align:right;color:#58a6ff">' + v.performance + 'x</td>' +
      '<td style="font-size:12px;text-align:right">' + formatNum(v.likes) + '</td>' +
      '<td style="text-align:center"><button class="btn btn-sm" onclick="openYtAnalysis(' + i + ')" style="font-size:11px">분석</button></td>' +
    '</tr>';
  }).join('');
  window._ytResults = videos;
}

function renderSuggestedTags(videos) {
  const tagCount = {};
  videos.forEach(v => {
    (v.tags || []).slice(0, 5).forEach(t => {
      if (t.length > 1 && t.length < 30) tagCount[t] = (tagCount[t] || 0) + 1;
    });
  });
  const sorted = Object.entries(tagCount).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const container = document.getElementById('yt-suggested-tags');
  container.innerHTML = sorted.map(([tag]) =>
    '<span class="yt-tag" onclick="document.getElementById(\'yt-search-query\').value=\'' +
    escHtml(tag).replace(/'/g, "\\'") + '\';searchYtVideos()">' + escHtml(tag) + '</span>'
  ).join('');
}

function openYtAnalysis(idx) {
  const v = (window._ytResults || [])[idx];
  if (!v) return;
  const viralLabel = v.contribution > 200 ? '🔥 바이럴' : v.contribution > 50 ? '📈 우수' : '📊 보통';
  const text =
    '━━━ 영상 분석 ━━━\n\n' +
    '제목: ' + v.title + '\n' +
    '채널: ' + v.channelTitle + ' (구독자 ' + formatNum(v.subs) + ')\n' +
    '게시일: ' + formatDate(v.publishedAt) + '\n' +
    '재생 시간: ' + parseDuration(v.duration) + '\n\n' +
    '━━━ 성과 지표 ━━━\n\n' +
    '조회수: ' + formatNum(v.views) + '\n' +
    '좋아요: ' + formatNum(v.likes) + '\n' +
    '댓글: ' + formatNum(v.comments) + '\n' +
    '채널 기여도: ' + v.contribution + '% (' + viralLabel + ')\n' +
    '구독자 대비 조회수: ' + v.performance + 'x\n\n' +
    '━━━ 평가 ━━━\n\n' +
    (v.contribution > 200
      ? '✅ 이 영상은 채널 평균 조회수보다 ' + v.contribution + '% 더 높은 성과를 기록했습니다. 바이럴 영상으로 분류됩니다.'
      : v.contribution > 50
        ? '✅ 채널 평균 대비 ' + v.contribution + '% 높은 성과입니다. 우수한 영상입니다.'
        : '📊 채널 평균 수준의 성과입니다.') + '\n' +
    (v.performance > 1
      ? '\n✅ 구독자 수보다 ' + v.performance + '배 많은 조회수 — 비구독자 노출이 매우 높습니다.'
      : '') + '\n\n' +
    '태그: ' + (v.tags || []).slice(0, 15).join(', ');
  document.getElementById('modal-title').textContent = '영상 분석';
  document.getElementById('modal-body').innerHTML =
    '<div style="margin-bottom:12px"><a href="https://youtube.com/watch?v=' + v.videoId + '" target="_blank" class="btn btn-sm">' +
    '&#x1F517; YouTube에서 보기</a></div>' +
    '<div class="yt-analysis-text">' + escHtml(text) + '</div>';
  document.getElementById('job-modal').style.display = 'flex';
}

/* ── Utility helpers ── */
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function formatNum(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(n);
}
function formatDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' + String(d.getDate()).padStart(2, '0');
}
function parseDuration(dur) {
  if (!dur) return '-';
  const m = dur.match(/PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?/);
  if (!m) return dur;
  const h = parseInt(m[1]) || 0, min = parseInt(m[2]) || 0, s = parseInt(m[3]) || 0;
  return (h ? h + ':' : '') + String(min).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

/* ── Autopilot functions ── */
let autopilotSettingsInitialized = false;
const ALL_CATEGORIES = ["탈북사연", "해외감동", "노후금융", "황혼19금", "옛날이야기", "한국사연", "무협", "경제"];

function toggleLimitInput() {
  const mode = document.getElementById('auto-setting-mode').value;
  document.getElementById('auto-limit-group').style.display = (mode === 'target_limit') ? 'block' : 'none';
}

function renderCategoryCheckboxes(activeCats) {
  const container = document.getElementById('auto-categories-checkboxes');
  if (!container) return;
  container.innerHTML = '';
  
  ALL_CATEGORIES.forEach(cat => {
    const isChecked = activeCats ? activeCats.includes(cat) : true;
    const label = document.createElement('label');
    label.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;color:#c9d1d9;cursor:pointer;background:rgba(255,255,255,0.02);padding:6px;border-radius:4px;border:1px solid rgba(255,255,255,0.05);';
    label.innerHTML = `
      <input type="checkbox" class="auto-cat-checkbox" value="${cat}" ${isChecked ? 'checked' : ''} style="cursor:pointer;" />
      <span>${cat}</span>
    `;
    container.appendChild(label);
  });
}

function renderActiveCategoryBadges(activeCats) {
  const categories = Array.isArray(activeCats) ? activeCats : ALL_CATEGORIES;
  const title = document.getElementById('auto-active-category-title');
  const container = document.getElementById('auto-active-category-badges');
  if (title) title.textContent = `설정된 카테고리 (${categories.length}개)`;
  if (!container) return;
  container.innerHTML = '';

  if (categories.length === 0) {
    const empty = document.createElement('span');
    empty.style.cssText = 'color:#8b949e;font-size:12px;';
    empty.textContent = '선택된 카테고리가 없습니다.';
    container.appendChild(empty);
    return;
  }

  categories.forEach(cat => {
    const badge = document.createElement('span');
    badge.className = 'badge badge-preparing';
    badge.textContent = cat;
    container.appendChild(badge);
  });
}

function getSettingsFromUI() {
  const mode = document.getElementById('auto-setting-mode').value;
  const limit = parseInt(document.getElementById('auto-setting-limit').value) || 10;
  const buffer = parseInt(document.getElementById('auto-setting-buffer').value) || 5;
  
  const checkboxes = document.querySelectorAll('.auto-cat-checkbox');
  const active_categories = [];
  checkboxes.forEach(cb => {
    if (cb.checked) active_categories.push(cb.value);
  });
  
  return {
    mode,
    target_limit: limit,
    min_buffer_per_category: buffer,
    active_categories
  };
}

async function saveAutopilotSettings() {
  const settings = getSettingsFromUI();
  try {
    const res = await api('POST', '/api/autopilot/hermes/save_settings', { settings });
    if (res && res.success) {
      const savedSettings = res.settings || settings;
      renderActiveCategoryBadges(savedSettings.active_categories);
      renderCategoryCheckboxes(savedSettings.active_categories);
      showToast('오토파일럿 설정이 저장되었습니다.', 'success');
    } else {
      showToast('설정 저장 실패: ' + (res?.error || '알 수 없음'), 'error');
    }
  } catch(e) {
    showToast('설정 저장 통신 실패', 'error');
  }
}

async function loadAutopilotStatus() {
  try {
    const data = await api('GET', '/api/autopilot/hermes/status');
    if (!data) return;
    
    const isRunning = data.is_running;
    document.getElementById('auto-btn-start').disabled = isRunning;
    document.getElementById('auto-btn-stop').disabled = !isRunning;
    
    const statusBadgeEl = document.getElementById('auto-status-text');
    if (isRunning) {
      statusBadgeEl.className = 'badge badge-running';
      statusBadgeEl.textContent = '동작 중';
    } else {
      statusBadgeEl.className = 'badge badge-stopped';
      statusBadgeEl.textContent = '중지됨';
    }
    
    document.getElementById('auto-info-running').innerHTML = isRunning ? '<span style="color:#3fb950;font-weight:bold;">실행 중</span>' : '중지됨';
    document.getElementById('auto-info-step').textContent = data.current_step || '-';
    document.getElementById('auto-info-category').textContent = data.current_category || '-';
    document.getElementById('auto-info-topic').textContent = data.current_topic || '-';
    document.getElementById('auto-info-image-style').textContent = data.current_image_style || '-';
    
    if (data.session_stats) {
      const generated = data.session_stats.generated_count || 0;
      document.getElementById('auto-info-generated').textContent = generated + ' 개';
    }

    if (data.settings) {
      renderActiveCategoryBadges(data.settings.active_categories);
    } else {
      renderActiveCategoryBadges(null);
    }
    
    // UI 초기화 (최초 1회만 설정 채워넣음)
    if (!autopilotSettingsInitialized && data.settings) {
      document.getElementById('auto-setting-mode').value = data.settings.mode || 'infinite';
      document.getElementById('auto-setting-limit').value = data.settings.target_limit || 10;
      document.getElementById('auto-setting-buffer').value = data.settings.min_buffer_per_category || 5;
      
      toggleLimitInput();
      renderCategoryCheckboxes(data.settings.active_categories);
      autopilotSettingsInitialized = true;
    } else if (!autopilotSettingsInitialized) {
      // 폰백 렌더링
      renderCategoryCheckboxes(null);
      autopilotSettingsInitialized = true;
    }
    
    const logsEl = document.getElementById('auto-logs');
    if (data.logs && data.logs.length > 0) {
      logsEl.textContent = data.logs.join('\n');
      logsEl.scrollTop = logsEl.scrollHeight;
    } else {
      logsEl.textContent = '로그가 없습니다.';
    }
  } catch(e) {
    console.error('loadAutopilotStatus error:', e);
  }
}

async function startAutopilot() {
  const settings = getSettingsFromUI();
  const startLimit = Number.parseInt(document.getElementById('auto-start-limit').value, 10);
  if (!Number.isInteger(startLimit) || startLimit < 1 || startLimit > 100) {
    showToast('생성 수는 1~100 사이로 입력하세요.', 'error');
    return;
  }
  settings.mode = 'target_limit';
  settings.target_limit = startLimit;
  document.getElementById('auto-setting-mode').value = 'target_limit';
  document.getElementById('auto-setting-limit').value = startLimit;
  toggleLimitInput();
  try {
    const res = await api('POST', '/api/autopilot/hermes/start', { settings });
    if (res && res.success) {
      showToast(`Hermes가 ${startLimit}개 생성 후 자동 정지합니다.`, 'success');
      loadAutopilotStatus();
    } else {
      showToast('자동 생성기 시작 실패: ' + (res?.error || '알 수 없음'), 'error');
    }
  } catch(e) {
    showToast('자동 생성기 시작 통신 실패', 'error');
  }
}

async function stopAutopilot() {
  try {
    const res = await api('POST', '/api/autopilot/hermes/stop');
    if (res && res.success) {
      showToast('Hermes 자동 생성기 중지 요청됨.', 'info');
      loadAutopilotStatus();
    } else {
      showToast('자동 생성기 중지 실패: ' + (res?.error || '알 수 없음'), 'error');
    }
  } catch(e) {
    showToast('자동 생성기 중지 통신 실패', 'error');
  }
}

/* ── Init ── */
refreshAll();
</script>
</body>
</html>"""
