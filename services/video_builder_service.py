"""
video_builder_service.py
웹툰 PNG 컷 + 대본 → Gemini Vision 분석 → 감독 연출 기획서 생성
Scene Builder 체인 방식 AI 영상 자동 생성 서비스
"""
import os
import json
import base64
import re
import httpx
from typing import List, Optional
from config import config


# ─────────────────────────────────────────────────────────────────────────────
# 감독 연출 기획서 생성 (Gemini Vision 다중 이미지)
# ─────────────────────────────────────────────────────────────────────────────

DIRECTOR_ANALYSIS_PROMPT = """
당신은 세계적인 애니메이션 영상 감독입니다.
웹툰 컷 이미지들과 대본 맥락을 분석하여, 관객이 영상을 보기 전에 이해할 수 있는 
**감독 연출 기획서**를 한국어로 작성해주세요.

[제공 정보]
- 총 씬 수: {total_scenes}개
- 대본/기획서 맥락: {script_context}
- 각 씬 이미지는 순서대로 첨부됩니다.

[작성 요령]
각 씬에 대해 아래 정보를 명확하고 생동감 있게 서술하세요:
1. 어떤 이미지(들)를 사용하는지 (간단한 시각적 묘사)
2. 전체적인 분위기/감정 (예: 긴장감, 슬픔, 웅장함, 설렘)
3. 카메라 움직임 (예: 천천히 줌인, 빠른 패닝, 정적인 고정, 위에서 아래로 내려오는 팬)
4. 전개 속도/리듬 (예: 느긋하게 여운을 남기며, 긴박하고 빠르게, 순간적으로 전환)
5. 다음 씬과의 연결 방식 (어떻게 자연스럽게 넘어가는지)
6. 영상 프롬프트 (Wan 2.1 AI 영상 생성용 영어 프롬프트, 40-60단어)

[반드시 JSON 형식으로만 반환]
{{
  "director_overview": "전체 영상의 감독 연출 방향을 2-3문장으로 요약 (한국어)",
  "overall_mood": "전체 영상의 분위기 키워드 3개",
  "estimated_duration": "예상 총 영상 길이 (예: 40초, 1분 20초)",
  "bgm_recommendation": "추천 BGM 스타일 (한국어)",
  "scenes": [
    {{
      "scene_id": 1,
      "image_desc": "이미지 시각적 묘사 (한국어, 1-2문장)",
      "mood": "이 씬의 분위기 (한국어)",
      "camera_motion": "카메라 움직임 한국어 설명 (예: 하늘에서 천천히 내려다보는 하향 팬)",
      "camera_motion_en": "camera motion in English (e.g., slow downward pan from above)",
      "pacing": "전개 속도 설명 (예: 느리고 장엄하게, 빠르고 긴박하게)",
      "director_note": "감독 연출 노트 — 관객에게 전달하려는 감정/의도 (한국어, 2-3문장으로 풍부하게)",
      "transition_to_next": "다음 씬으로의 전환 방식 (없으면 null)",
      "motion_prompt": "Wan 2.1 AI video generation prompt in English (40-60 words, cinematic)",
      "duration_suggestion": 5.0
    }}
  ]
}}

RETURN JSON ONLY. NO MARKDOWN. NO EXPLANATION.
"""


async def analyze_scenes_for_director(
    png_paths: List[str],
    script_context: str = "",
) -> dict:
    """
    PNG 컷 이미지 목록을 Gemini Vision으로 분석하여
    감독 연출 기획서 JSON 반환.
    """
    api_key = config.GEMINI_API_KEY
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    safe_context = script_context.strip() if script_context else "대본 없음"
    total_scenes = len(png_paths)

    prompt_text = DIRECTOR_ANALYSIS_PROMPT.format(
        total_scenes=total_scenes,
        script_context=safe_context[:2000],  # 토큰 제한
    )

    # 멀티 이미지 parts 구성 (최대 8장 제한 — Gemini Flash 권장)
    parts = [{"text": prompt_text}]
    max_images = min(total_scenes, 8)

    for idx in range(max_images):
        img_path = png_paths[idx]
        if not os.path.exists(img_path):
            continue
        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()
            encoded = base64.b64encode(img_bytes).decode("utf-8")
            ext = os.path.splitext(img_path)[1].lower()
            mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                        ".png": "image/png", ".webp": "image/webp"}
            mime_type = mime_map.get(ext, "image/png")

            # 씬 번호 텍스트 삽입
            parts.append({"text": f"\n[씬 {idx + 1} 이미지]"})
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": encoded
                }
            })
        except Exception as e:
            print(f"[VideoBuilder] Image load error ({img_path}): {e}")

    # 이미지가 8개 초과시 나머지는 경로만 제공
    if total_scenes > max_images:
        remaining = total_scenes - max_images
        parts.append({
            "text": f"\n(나머지 {remaining}개 씬은 이전 씬들의 스타일을 참고하여 연속성 있게 기획해주세요.)"
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 8192
        }
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()

        if "candidates" not in result:
            error_msg = result.get("error", {}).get("message", str(result))
            raise Exception(f"Gemini API 오류: {error_msg}")

        raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
        print(f"[VideoBuilder] Gemini raw response length: {len(raw_text)}")

        # JSON 파싱
        cleaned = re.sub(r"```json\s*|\s*```", "", raw_text).strip()
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            parsed = json.loads(json_match.group())

            # 이미지가 8개 초과했을 때 나머지 씬 placeholder 추가
            existing_ids = {s["scene_id"] for s in parsed.get("scenes", [])}
            for i in range(1, total_scenes + 1):
                if i not in existing_ids:
                    parsed["scenes"].append({
                        "scene_id": i,
                        "image_desc": f"씬 {i} — 이전 분위기 연속",
                        "mood": "연속",
                        "camera_motion": "이전 씬과 유사한 카메라 움직임",
                        "camera_motion_en": "similar camera motion as previous scene",
                        "pacing": "자연스럽게",
                        "director_note": f"씬 {i}는 이전 흐름을 이어받아 전개됩니다.",
                        "transition_to_next": None,
                        "motion_prompt": "Cinematic vertical animation, smooth camera motion, high quality webtoon style, atmospheric lighting, emotional pacing.",
                        "duration_suggestion": 5.0
                    })

            # scene_id 기준 정렬
            parsed["scenes"] = sorted(parsed["scenes"], key=lambda x: x.get("scene_id", 0))

            # 실제 이미지 경로 추가
            for scene in parsed["scenes"]:
                sid = scene.get("scene_id", 1)
                img_idx = sid - 1
                if 0 <= img_idx < len(png_paths):
                    scene["image_path"] = png_paths[img_idx]
                    scene["image_filename"] = os.path.basename(png_paths[img_idx])
                else:
                    scene["image_path"] = ""
                    scene["image_filename"] = ""

            parsed["total_scenes"] = total_scenes
            parsed["analyzed_images"] = max_images
            return parsed

        raise Exception("JSON 파싱 실패")

    except Exception as e:
        print(f"[VideoBuilder] analyze_scenes_for_director error: {e}")
        # 폴백: 기본 템플릿 반환
        return _fallback_director_plan(png_paths)


def _fallback_director_plan(png_paths: List[str]) -> dict:
    """Gemini 실패 시 기본 연출 기획서 반환"""
    scenes = []
    for i, p in enumerate(png_paths):
        scenes.append({
            "scene_id": i + 1,
            "image_desc": f"씬 {i+1} ({os.path.basename(p)})",
            "mood": "분석 실패 — 직접 입력 필요",
            "camera_motion": "천천히 줌인",
            "camera_motion_en": "slow zoom in",
            "pacing": "보통 속도",
            "director_note": "Gemini 분석에 실패하였습니다. 직접 수정해주세요.",
            "transition_to_next": "컷 전환" if i < len(png_paths) - 1 else None,
            "motion_prompt": "Cinematic vertical animation, smooth camera motion, high quality webtoon style.",
            "duration_suggestion": 5.0,
            "image_path": p,
            "image_filename": os.path.basename(p)
        })
    return {
        "director_overview": "분석 실패 — 직접 수정이 필요합니다.",
        "overall_mood": "미정",
        "estimated_duration": f"{len(png_paths) * 5}초",
        "bgm_recommendation": "미정",
        "scenes": scenes,
        "total_scenes": len(png_paths),
        "analyzed_images": 0
    }


def get_png_files_from_folder(folder_path: str) -> List[str]:
    """폴더에서 PNG/JPG 파일 목록 반환 (정렬됨)"""
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = []
    if not os.path.isdir(folder_path):
        return files
    for f in sorted(os.listdir(folder_path)):
        ext = os.path.splitext(f)[1].lower()
        if ext in valid_exts:
            files.append(os.path.join(folder_path, f))
    return files


# ─────────────────────────────────────────────────────────────────────────────
# Scene Builder 체인 — 영상 생성 (Wan 2.1 → AKOOL 폴백)
# ─────────────────────────────────────────────────────────────────────────────

class SceneVideoResult:
    def __init__(self, scene_id: int, video_path: str = "", last_frame_path: str = "",
                 status: str = "pending", engine: str = "", error: str = ""):
        self.scene_id = scene_id
        self.video_path = video_path
        self.last_frame_path = last_frame_path
        self.status = status  # pending | success | error | skipped
        self.engine = engine  # wan | akool | fallback
        self.error = error

    def to_dict(self):
        return {
            "scene_id": self.scene_id,
            "video_path": self.video_path,
            "last_frame_path": self.last_frame_path,
            "status": self.status,
            "engine": self.engine,
            "error": self.error,
        }


async def generate_scene_video_wan(
    image_path: str,
    prompt: str,
    output_dir: str,
    scene_id: int,
) -> Optional[str]:
    """
    Wan 2.1 i2v로 단일 씬 영상 생성.
    성공 시 video_path 반환, 실패 시 None
    """
    try:
        from services.replicate_service import replicate_service
        print(f"[VB] 🎬 씬 {scene_id} — Wan 2.1 시도 중...")

        video_bytes = await replicate_service.generate_video_from_image(
            image_path=image_path,
            prompt=prompt,
            duration=5.0,
            method="standard",
        )
        if not video_bytes:
            raise Exception("Wan 2.1: 빈 응답 (크레딧 부족 또는 서버 오류)")

        out_path = os.path.join(output_dir, f"scene_{scene_id:03d}_wan.mp4")
        with open(out_path, "wb") as f:
            f.write(video_bytes)
        print(f"[VB] ✅ 씬 {scene_id} — Wan 2.1 완료: {out_path}")
        return out_path

    except Exception as e:
        err = str(e).lower()
        # 크레딧 부족 / 결제 필요 키워드 감지
        is_credit_error = any(k in err for k in [
            "credit", "billing", "payment", "quota", "insufficient",
            "rate limit", "429", "throttle", "balance", "no_credits"
        ])
        if is_credit_error:
            print(f"[VB] ⚠️ 씬 {scene_id} — Wan 크레딧 부족, AKOOL로 전환: {e}")
        else:
            print(f"[VB] ❌ 씬 {scene_id} — Wan 오류: {e}")
        return None


async def generate_scene_video_akool(
    image_path: str,
    prompt: str,
    output_dir: str,
    scene_id: int,
) -> Optional[str]:
    """
    AKOOL Image-to-Video API로 단일 씬 영상 생성.
    이미지를 먼저 임시 URL에 업로드(base64 → data URL) 후 API 호출.
    성공 시 video_path 반환, 실패 시 None
    """
    akool_token = (
        os.getenv("AKOOL_TOKEN")
        or os.getenv("AKOOL_CLIENT_ID")
        or getattr(config, "AKOOL_TOKEN", "")
        or getattr(config, "AKOOL_CLIENT_ID", "")
    )
    if not akool_token:
        print(f"[VB] ❌ AKOOL 토큰 없음 — 씬 {scene_id} 건너뜀")
        return None

    try:
        from services.akool_service import akool_service
        print(f"[VB] 🔄 씬 {scene_id} — AKOOL 시도 중...")

        # akool_service 모듈 재사용 (내부에서 이미지 업로드, 폴링, 다운로드 모두 처리)
        video_bytes = await akool_service.generate_seedance_video(
            local_image_path=image_path,
            prompt=prompt[:500], # 최대 500자
            duration=5,
            resolution="720p"
        )
        
        if not video_bytes:
            raise Exception("AKOOL 영상 반환 안됨")

        out_path = os.path.join(output_dir, f"scene_{scene_id:03d}_akool.mp4")
        with open(out_path, "wb") as f:
            f.write(video_bytes)
        print(f"[VB] ✅ 씬 {scene_id} — AKOOL 완료: {out_path}")
        return out_path
    except Exception as e:
        print(f"[VB] ❌ 씬 {scene_id} — AKOOL 오류: {e}")
        return None





def _extract_last_frame(video_path: str, output_dir: str, scene_id: int) -> Optional[str]:
    """
    영상의 마지막 프레임을 PNG로 추출.
    성공 시 이미지 경로 반환, 실패 시 None
    """
    try:
        from services.video_service import video_service
        frame_path = os.path.join(output_dir, f"lastframe_{scene_id:03d}.png")
        ok = video_service.extract_last_frame(video_path, frame_path)
        if ok and os.path.exists(frame_path):
            print(f"[VB] 🖼️ 씬 {scene_id} 마지막 프레임 추출: {frame_path}")
            return frame_path
    except Exception as e:
        print(f"[VB] 마지막 프레임 추출 실패 (씬 {scene_id}): {e}")
    return None


def _blend_frames(prev_frame: str, next_image: str, output_dir: str, scene_id: int, alpha: float = 0.25) -> str:
    """
    이전 씬 마지막 프레임 + 다음 씬 PNG를 블렌딩하여 부드러운 전환 이미지 생성.
    alpha=0.25: 이전 프레임 25% + 새 이미지 75%
    """
    try:
        from PIL import Image
        img_prev = Image.open(prev_frame).convert("RGBA")
        img_next = Image.open(next_image).convert("RGBA")

        # 크기 통일 (next_image 크기 기준)
        if img_prev.size != img_next.size:
            img_prev = img_prev.resize(img_next.size, Image.LANCZOS)

        blended = Image.blend(img_prev, img_next, alpha=(1 - alpha))
        out_path = os.path.join(output_dir, f"blend_{scene_id:03d}.png")
        blended.convert("RGB").save(out_path)
        print(f"[VB] 🎨 씬 {scene_id} 블렌드 이미지 생성: {out_path}")
        return out_path
    except Exception as e:
        print(f"[VB] 블렌드 실패 (씬 {scene_id}): {e} — 원본 이미지 사용")
        return next_image  # 실패 시 원본 사용


async def run_scene_builder_chain(
    scenes: list,
    output_dir: str,
    on_progress=None,
) -> List[SceneVideoResult]:
    """
    Scene Builder 체인 실행:
    씬1 PNG → 영상1 → 마지막프레임1 + 씬2 PNG 블렌드 → 영상2 → ... → 영상N

    on_progress: async callable(scene_id, status, message) — SSE 진행률 콜백
    반환: List[SceneVideoResult]
    """
    os.makedirs(output_dir, exist_ok=True)
    results: List[SceneVideoResult] = []
    last_frame_path: Optional[str] = None

    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", i + 1)
        image_path = scene.get("image_path", "")
        motion_prompt = scene.get("motion_prompt", "")
        duration = float(scene.get("duration_suggestion", 5.0))

        result = SceneVideoResult(scene_id=scene_id)

        if on_progress:
            await on_progress(scene_id, "generating",
                              f"씬 {scene_id}/{len(scenes)} 영상 생성 중...")

        # ── 시작 이미지 결정 ──────────────────────────────────────────────
        if last_frame_path and os.path.exists(last_frame_path) and image_path:
            # 이전 씬 마지막 프레임 + 현재 씬 이미지 블렌딩
            start_image = _blend_frames(last_frame_path, image_path, output_dir, scene_id)
        elif image_path and os.path.exists(image_path):
            start_image = image_path
        else:
            print(f"[VB] 씬 {scene_id}: 이미지 없음 — 건너뜀")
            result.status = "skipped"
            result.error = f"이미지 파일 없음: {image_path}"
            results.append(result)
            continue

        # ── 영상 생성: Wan 2.1 우선 → AKOOL 폴백 ─────────────────────────
        video_path = await generate_scene_video_wan(start_image, motion_prompt, output_dir, scene_id)
        result.engine = "wan"

        if not video_path:
            # Wan 실패 → AKOOL 폴백
            video_path = await generate_scene_video_akool(start_image, motion_prompt, output_dir, scene_id)
            result.engine = "akool"

        # ── 결과 처리 ─────────────────────────────────────────────────────
        if video_path and os.path.exists(video_path):
            result.video_path = video_path
            result.status = "success"

            # 마지막 프레임 추출 (다음 씬 연결용)
            frame = _extract_last_frame(video_path, output_dir, scene_id)
            if frame:
                result.last_frame_path = frame
                last_frame_path = frame
            else:
                last_frame_path = None  # 추출 실패 시 다음 씬은 원본 이미지 사용

            if on_progress:
                await on_progress(scene_id, "done",
                                  f"씬 {scene_id} 완료 ({result.engine})")
        else:
            result.status = "error"
            result.error = "Wan 2.1 및 AKOOL 모두 실패"
            last_frame_path = None
            if on_progress:
                await on_progress(scene_id, "error", f"씬 {scene_id} 실패")

        results.append(result)
        print(f"[VB] 씬 {scene_id} → {result.status} ({result.engine}), path={result.video_path}")

    return results


async def concat_scene_videos(
    results: List[SceneVideoResult],
    output_dir: str,
) -> Optional[str]:
    """
    성공한 씬 영상들을 하나로 합쳐 최종 영상 반환.
    """
    try:
        from services.video_service import video_service
        video_paths = [r.video_path for r in results if r.status == "success" and r.video_path]
        if not video_paths:
            return None

        import time
        final_path = os.path.join(output_dir, f"final_{int(time.time())}.mp4")
        result = video_service.concatenate_videos(video_paths, final_path)
        if result and os.path.exists(result):
            print(f"[VB] ✅ 최종 영상 합본: {result}")
            return result
    except Exception as e:
        print(f"[VB] 최종 합본 실패: {e}")
    return None
