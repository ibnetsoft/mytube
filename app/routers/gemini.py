"""
Gemini API 라우터
/api/gemini/* 및 /api/nursery/* 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import httpx
import json

import database as db
from config import config
from app.models.media import GeminiRequest
from services.gemini_service import gemini_service

router = APIRouter(tags=["Gemini"])


class StructureGenerateRequest(BaseModel):
    project_id: Optional[int] = None
    topic: str
    duration: int = 60
    tone: str = "informative"
    notes: Optional[str] = None
    target_language: Optional[str] = "ko"
    script_style: Optional[str] = "story"
    mode: str = "monologue"


class AnalysisRequest(BaseModel):
    video_id: str
    title: str
    channel_title: str
    description: str = ""
    tags: List[str] = []
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    published_at: str = ""
    thumbnail_url: str = ""
    transcript: Optional[str] = None


class NurseryDevelopRequest(BaseModel):
    title: str
    summary: str
    project_id: Optional[int] = None


class NurseryImagePromptsRequest(BaseModel):
    title: str
    lyrics: str
    project_id: Optional[int] = None


def _sync_claimed_topic_pregeneration(project_id: int, settings: dict) -> dict:
    """Refresh a claimed topic's Worker output into the local project cache."""
    topic_id = str(settings.get("topic_queue_id") or "").strip()
    if not topic_id:
        return settings

    try:
        from app.routers.user_topics import (
            _call_bridge,
            _copy_prepared_topic_assets_to_project,
            _copy_publish_metadata_to_project,
            _is_fully_prepared_topic,
        )

        result = _call_bridge("get_claimed_topic_pregeneration", {"topic_id": topic_id})
        if result.get("status") != "ok":
            return settings
        topic = result.get("topic") or {}
        progress_payload = topic.get("progress_payload") or {}
        if isinstance(progress_payload, str):
            try:
                progress_payload = json.loads(progress_payload)
            except json.JSONDecodeError:
                progress_payload = {}
        if not isinstance(progress_payload, dict):
            progress_payload = {}
        structure_status = topic.get("pregenerated_structure_status") or "queued"
        script_status = topic.get("pregenerated_script_status") or "queued"
        db.update_project_setting(project_id, "pregenerated_structure_status", structure_status)
        db.update_project_setting(project_id, "pregenerated_script_status", script_status)

        structure = topic.get("pregenerated_structure")
        if structure_status == "ready" and structure:
            db.update_project_setting(
                project_id, "pregenerated_structure_json", json.dumps(structure, ensure_ascii=False)
            )
        script = topic.get("pregenerated_script")
        if script_status == "ready" and script:
            db.update_project_setting(project_id, "pregenerated_script_text", script)
        has_ready_structure = structure_status == "ready" and bool(structure)
        has_ready_script = script_status == "ready" and bool(script)
        if has_ready_structure or has_ready_script:
            _copy_prepared_topic_assets_to_project(project_id, topic)

        generated_title = str(topic.get("generated_title") or "").strip()
        if generated_title:
            db.update_project_setting(project_id, "generated_title", generated_title)
        if not _copy_publish_metadata_to_project(project_id, topic, generated_title) and generated_title:
            db.save_metadata(project_id, [generated_title], "", [], [])
        benchmark = topic.get("benchmark_analysis")
        if benchmark:
            db.update_project_setting(
                project_id, "benchmark_analysis_json", json.dumps(benchmark, ensure_ascii=False)
            )
        sfx_cues_json = progress_payload.get("sfx_cues_json")
        sfx_cues = progress_payload.get("sfx_cues")
        if sfx_cues_json:
            db.update_project_setting(project_id, "sfx_cues_json", str(sfx_cues_json))
        elif isinstance(sfx_cues, list):
            db.update_project_setting(project_id, "sfx_cues_json", json.dumps(sfx_cues, ensure_ascii=False))
        return db.get_project_settings(project_id) or settings
    except Exception as exc:
        print(f"[Gemini] Failed to refresh pregeneration for project {project_id}: {exc}")
        return settings


@router.post("/api/projects/{project_id}/refresh-pregeneration")
async def refresh_claimed_topic_pregeneration(project_id: int):
    """Expose the latest claimed-topic preparation state to the desktop UI."""
    from services.auth_service import auth_service

    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    email = auth_service.get_user_email()
    if not email or project.get("employee_email") != email:
        raise HTTPException(status_code=403, detail="Project access denied")

    settings = db.get_project_settings(project_id) or {}
    return {"status": "ok", "settings": _sync_claimed_topic_pregeneration(project_id, settings)}


@router.post("/api/gemini/generate-structure")
async def generate_script_structure_api(req: StructureGenerateRequest):
    """대본 구조 생성 (중복 방지 적용)"""
    # [AIR-0230 §2d] 사전생성 버퍼 - claim_topic()이 pregenerated_structure_json을
    # project_settings에 이미 복사해뒀으면(웹어드민이 주제 생성 직후 미리 기획을
    # 만들어둔 경우), AI를 다시 부르지 않고 그 값을 즉시 반환한다. 크레딧 체크보다도
    # 먼저 해야 한다 - 어차피 AI 호출이 없으니 크레딧을 쓸 이유가 없음.
    #
    # [AIR-0230, 사용자 결정] STD의 claim-큐 흐름은 실시간 생성 폴백을 완전히
    # 제거한다 - 사전생성이 준비 안 됐으면 AI를 대신 부르지 않고 대기 상태를
    # 반환한다. project_settings.topic_queue_id 존재 여부로 "이 프로젝트가
    # topics_queue에서 claim된 것인지"를 판단한다 - PRO의 수동 생성 프로젝트는
    # topic_queue_id가 없고 애초에 사전생성 대상이 아니므로(웹어드민이 만든 큐를
    # 거치지 않음) 실시간 생성이 유일한 경로로 그대로 유지된다.
    if req.project_id:
        settings = db.get_project_settings(req.project_id) or {}
        if settings.get("topic_queue_id"):
            settings = _sync_claimed_topic_pregeneration(req.project_id, settings)
            raw = settings.get("pregenerated_structure_json")
            if raw:
                try:
                    pregenerated = json.loads(raw)
                    if pregenerated and pregenerated.get("scenes"):
                        return {"status": "ok", "structure": pregenerated, "pregenerated": True}
                except Exception as e:
                    print(f"[Gemini] Failed to parse pregenerated_structure for project {req.project_id}: {e}")

            if settings.get("pregenerated_structure_status") == "failed":
                return {
                    "status": "error",
                    "error": "AI Worker failed to prepare this plan. Please try another topic or contact the administrator.",
                    "pregeneration_status": "failed",
                }
            return {
                "status": "pending",
                "error": "이 주제는 아직 기획이 준비되지 않았습니다. 잠시 후 다시 시도해주세요.",
                "pregeneration_status": settings.get("pregenerated_structure_status") or "queued",
            }

    from services.auth_service import auth_service
    if not auth_service.check_credits(500):
        return {"status": "error", "error": "AI 토큰이 부족합니다. 어드민 페이지에서 충전 후 이용해주세요."}

    try:
        recent_projects = db.get_recent_projects(limit=5)
        recent_titles = [p['name'] for p in recent_projects]

        from services.script_style_resolver import resolve_script_style_directive
        style_directive = resolve_script_style_directive(req.script_style)

        db_analysis = None
        queue_benchmark_analysis = None
        upload_title = ""
        title_generation = {}
        if req.project_id:
            db_analysis = db.get_analysis(req.project_id)
            settings = db.get_project_settings(req.project_id) or {}
            upload_title = settings.get("generated_title") or settings.get("title") or ""
            raw_title_generation = settings.get("title_generation_json")
            if raw_title_generation:
                try:
                    title_generation = json.loads(raw_title_generation)
                except Exception:
                    title_generation = {}
            if not db_analysis:
                # [AIR-0230 §2c] db_analysis is PRO's manual "search a video ->
                # analyze" path (templates/pages/topic.html) - STD claimed
                # topics never populate that local `analysis` table at all, so
                # without this fallback STD projects always get an empty
                # benchmark_analysis here regardless of what the web-admin's
                # topic_benchmark_analyze pipeline already found. claim_topic()
                # (app/routers/user_topics.py) copies topics_queue.benchmark_analysis
                # into this project_setting when present.
                try:
                    raw = settings.get("benchmark_analysis_json")
                    if raw:
                        # worker/hermes_worker.py's result_payload shape is
                        # {..., candidates: [{..., analysis: {...}}]} - one
                        # entry per analyzed video (usually just 1, see
                        # DEFAULT_BENCHMARK_CANDIDATES). Normalize to the same
                        # single-video "analysis" shape db_analysis.analysis_result
                        # already has, so the rest of this function (and
                        # scene_planner.plan_scenes()'s benchmark_analysis
                        # param) doesn't need to know which source it came from.
                        parsed = json.loads(raw)
                        candidates = parsed.get("candidates") or []
                        if candidates:
                            queue_benchmark_analysis = candidates[0].get("analysis")
                except Exception as e:
                    print(f"[Gemini] Failed to load queue benchmark_analysis for project {req.project_id}: {e}")

        duration_str = f"{req.duration}초"

        analysis_data = {
            "topic": req.topic,
            "duration_category": duration_str,
            "tone": req.tone,
            "user_notes": req.notes,
            "script_style": req.script_style,
            "success_analysis": (db_analysis.get("analysis_result") if db_analysis else None) or queue_benchmark_analysis
        }

        accumulated_knowledge = db.get_recent_knowledge(limit=10, script_style=req.script_style)

        from app.services.scene_planner import scene_planner_service
        result = await scene_planner_service.plan_scenes(
            topic=req.topic,
            target_duration=req.duration,
            project_id=req.project_id,
            style_directive=style_directive,
            # [FIX] 이 값들은 예전부터 조회만 되고 실제로는 전달되지 않던 값들이다 —
            # scene_planner가 GeminiService.generate_script_structure()로 대체되면서
            # 벤치마크 분석/누적 학습지식/최근주제 회피가 전부 죽은 코드가 됐었다.
            benchmark_analysis=analysis_data.get("success_analysis"),
            upload_title=upload_title,
            title_generation=title_generation,
            accumulated_knowledge=accumulated_knowledge,
            recent_titles=recent_titles,
        )

        # [FIX] scene_planner_service.plan_scenes()의 실패 응답은 error/error_message를
        # 최상위가 아니라 planner_notes 안에 담는다. 기존에는 최상위 result["error"]만
        # 확인해 이 조건이 절대 참이 되지 않았고, 실패해도 "status": "ok" + 빈 scenes[]가
        # 그대로 프론트로 나가 사용자에게는 "성공했지만 장면이 하나도 없는" 상태로 보였다.
        planner_notes = result.get("planner_notes") or {}
        if result.get("error") or planner_notes.get("error"):
            error_msg = result.get("error_message") or planner_notes.get("error_message") or "Unknown error"
            return {"status": "error", "error": error_msg}

        return {"status": "ok", "structure": result}

    except Exception as e:
        import traceback
        error_msg = f"Server Error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return {"status": "error", "error": f"서버 내부 오류: {str(e)}"}


@router.post("/api/gemini/deep-dive")
async def generate_deep_dive_script_api(req: StructureGenerateRequest):
    """여러 소스를 학습하여 고품질 '딥다이브' 대본 생성"""
    from services.auth_service import auth_service
    if not auth_service.check_credits(1000):
        return {"status": "error", "error": "AI 토큰이 부족합니다. (딥다이브 최소 1,000 TK 필요)"}

    if not req.project_id:
        return {"status": "error", "error": "project_id is required for deep-dive"}

    try:
        result = await gemini_service.generate_deep_dive_script(
            project_id=req.project_id,
            topic=req.topic,
            duration_seconds=req.duration,
            target_language=req.target_language or "ko",
            user_notes=req.notes or "없음",
            mode=req.mode
        )

        if "error" in result:
            return {"status": "error", "error": result["error"]}

        return {"status": "ok", "result": result}

    except Exception as e:
        print(f"[Deep Dive Error] {e}")
        return {"status": "error", "error": str(e)}


@router.post("/api/gemini/generate")
async def gemini_generate(req: GeminiRequest):
    """Gemini 텍스트 생성 (로깅 지원)"""
    from services.auth_service import auth_service
    if not auth_service.check_credits(200):
        return {"status": "error", "error": "AI 토큰이 부족합니다."}

    try:
        text = await gemini_service.generate_text(
            req.prompt,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            task_type="manual_gen"
        )
        return {"status": "ok", "text": text}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/script/generate")
async def script_generate(req: GeminiRequest):
    """대본 생성 (웹어드민의 '대본 생성 모델' 설정을 ai_router로 존중 - Claude/Gemini 자동 라우팅 + 실패 시 Gemini 폴백)"""
    from services.auth_service import auth_service
    from services import ai_router
    if not auth_service.check_credits(200):
        return {"status": "error", "error": "AI 토큰이 부족합니다."}

    try:
        config.refresh_remote_keys_if_stale()
        selected_model = config.SCRIPT_GENERATION_MODEL or config.SCRIPT_PLANNING_MODEL

        prompt = req.prompt
        # script_style이 없는 기존 호출(다른 /api/gemini/generate류 사용처 포함)은
        # 하위 호환을 위해 프롬프트를 그대로 사용한다.
        if req.script_style is not None:
            from services.script_style_resolver import resolve_script_style_directive
            style_directive = resolve_script_style_directive(req.script_style)
            if style_directive:
                prompt = f"{prompt}\n\n{style_directive}"

        text = await ai_router.generate_text(
            prompt,
            selected_model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            task_type="script_gen"
        )
        return {"status": "ok", "text": text}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/gemini/analyze-comments")
async def gemini_analyze_comments(req: AnalysisRequest):
    """비디오 종합 분석 (댓글 + 자막)"""
    # 1. 댓글 가져오기
    from services.youtube_data_api import async_youtube_get

    params = {
        "part": "snippet",
        "videoId": req.video_id,
        "maxResults": 50,
        "order": "relevance",
    }
    comments_data = await async_youtube_get("commentThreads", params)

    comments = []
    if "items" in comments_data:
        for item in comments_data["items"]:
            snippet = item["snippet"].get("topLevelComment", {}).get("snippet", {})
            text = snippet.get("textDisplay", "")
            if text:
                comments.append(text)

    # 2. Gemini 분석
    try:
        analysis = await gemini_service.analyze_comments(
            comments=comments,
            video_title=req.title,
            transcript=req.transcript
        )

        if "error" in analysis:
            return {"status": "error", "error": analysis["error"]}

        return {"status": "ok", "analysis": analysis, "comment_count": len(comments)}

    except Exception as e:
        print(f"분석 실패: {e}")
        return {"status": "error", "error": str(e)}


# --- Nursery Rhyme (동요) 전용 엔드포인트 ---

@router.get("/api/nursery/ideas")
async def get_nursery_ideas():
    """동요 아이디어 10개 생성"""
    try:
        ideas = await gemini_service.generate_nursery_rhyme_ideas()
        return {"status": "ok", "ideas": ideas}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/nursery/develop")
async def develop_nursery_song_api(req: NurseryDevelopRequest):
    """아이디어를 기반으로 동요 가사 및 구성 개발"""
    try:
        result = await gemini_service.develop_nursery_song(req.title, req.summary)
        if not result:
            return {"status": "error", "error": "노래 생성 실패"}
        return {"status": "ok", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/api/nursery/image-prompts")
async def generate_nursery_image_prompts_api(req: NurseryImagePromptsRequest):
    """가사 기반 3D 애니메이션 스타일 이미지 프롬프트 생성"""
    try:
        scenes = await gemini_service.generate_nursery_image_prompts(req.title, req.lyrics)
        if not scenes:
            return {"status": "error", "error": "이미지 프롬프트 생성 실패"}
        return {"status": "ok", "scenes": scenes}
    except Exception as e:
        return {"status": "error", "error": str(e)}
@router.get("/api/logs")
async def get_ai_logs_api(limit: int = 100, days: int = None):
    """AI 생성 로그 목록 조회 (필터 추가)"""
    try:
        logs = db.get_ai_logs(limit=limit, days=days)
        return {"status": "ok", "logs": logs}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.get("/api/logs/daily-usage")
async def get_daily_usage_api():
    """오늘 하루 총 토큰 사용량 조회"""
    try:
        total = db.get_daily_token_usage()
        return {"status": "ok", "total_tokens": total}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.delete("/api/logs")
async def clear_ai_logs_api():
    """AI 생성 로그 초기화"""
    try:
        db.clear_ai_logs()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
