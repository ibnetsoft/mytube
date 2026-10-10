"""업로드된 이미지/영상 클립을 씬에 매칭하는 AI 비전 대조기.

[재설계] 기존에는 씬의 대본 텍스트만 Gemini에 주고 "이 프레임이 몇 번
씬이냐"를 물었다 - 롱폼은 같은 인물/화풍 장면이 반복돼 텍스트만으로는
구분이 안 되는 경우가 많았다. 실제 워크플로우(씬 이미지를 외부 툴에 넣어
영상화)에서는 각 씬에 이미 '정답 이미지'가 붙어 있으므로, 이제 씬의
레퍼런스 이미지를 함께 보내 이미지 대 이미지 대조로 판단시킨다.

수정된 과거 버그: 씬 목록을 enumerate 인덱스+1로 번호 매겨 보냈다 -
실제 scene_number가 1..N 연속이 아니면 조용히 엉뚱한 씬에 매칭됐다.
이제 실제 scene_number를 쓴다.
"""
import os
import json
import base64
import io
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from moviepy import VideoFileClip
except ImportError:
    from moviepy.editor import VideoFileClip
from PIL import Image

from services.gemini_service import gemini_service

# Gemini에 보내는 이미지의 최대 변 길이. 대조 목적에는 충분하고
# 페이로드/토큰 비용을 크게 줄인다.
_MAX_SIDE = 512


def _downscale_to_jpeg(image_bytes: bytes) -> Tuple[bytes, str]:
    """이미지를 512px 이하 JPEG로 축소. 실패 시 원본 그대로 반환."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        img.thumbnail((_MAX_SIDE, _MAX_SIDE))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, "image/png"


def _frame_is_flat(frame) -> bool:
    """암전/단색(페이드 등) 프레임인지 - 표준편차가 낮으면 비대표 프레임."""
    try:
        img = Image.fromarray(frame).convert("L")
        img.thumbnail((64, 64))
        pixels = list(img.getdata())
        mean = sum(pixels) / len(pixels)
        var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        return var ** 0.5 < 10.0
    except Exception:
        return False


class VideoMatcher:
    @staticmethod
    def extract_middle_frame_bytes(video_path: str) -> bytes:
        """영상의 대표 프레임 1장을 PNG 바이트로 추출.

        중간(50%) 지점이 암전/페이드 프레임이면 25%/75% 지점을 대신
        시도한다 - 페이드 전환이 걸린 영상에서 새까만 프레임이 Gemini로
        가는 것을 막는다.
        """
        clip = None
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration or 0
            candidates = [0.5, 0.25, 0.75]
            frame = None
            for ratio in candidates:
                candidate = clip.get_frame(max(0.0, duration * ratio))
                if not _frame_is_flat(candidate):
                    frame = candidate
                    break
                if frame is None:
                    frame = candidate  # 전부 단색이면 첫 후보라도 사용

            img = Image.fromarray(frame)
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format="PNG")
            return img_byte_arr.getvalue()
        except Exception as e:
            print(f"Error extracting frame from {video_path}: {e}")
            raise e
        finally:
            if clip is not None:
                try:
                    clip.close()
                except Exception:
                    pass

    @classmethod
    async def match_assets_to_scenes(
        cls,
        project_id: int,
        uploaded_assets: List[Tuple[str, bytes, str]],  # (filename, frame/image bytes, mime)
        scene_refs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """업로드 에셋들을 씬에 매칭한다.

        scene_refs: [{"scene_number": int, "description": str,
                      "image_bytes": Optional[bytes]}]
        레퍼런스 이미지가 있는 씬은 이미지 대 이미지 대조, 없는 씬은
        텍스트 설명만으로 판단된다.

        반환: {filename: {"scene": int, "confidence": "high|medium|low"}}
        """
        if not uploaded_assets:
            return {}

        if scene_refs is None:
            # 하위 호환: 호출자가 레퍼런스를 안 넘기면 DB에서 텍스트만 구성
            import database as db
            p_data = db.get_image_prompts(project_id)
            if not p_data:
                print(f"[VideoMatcher] No image prompts found for project {project_id}")
                return {}
            scene_refs = [
                {
                    "scene_number": int(item.get("scene_number") or 0),
                    "description": item.get("scene_text") or item.get("scene") or item.get("prompt_ko") or "",
                    "image_bytes": None,
                }
                for item in p_data
                if int(item.get("scene_number") or 0) > 0
            ]

        if not scene_refs:
            return {}

        valid_numbers = sorted({int(ref["scene_number"]) for ref in scene_refs})

        # ---- 프롬프트 구성 --------------------------------------------------
        # 씬 정보(텍스트) 먼저, 이어서 각 씬의 레퍼런스 이미지, 마지막에
        # 매칭 대상 파일들. Gemini가 "이 프레임이 어느 레퍼런스와 같은
        # 장면인가"를 판단하도록 지시한다.
        scenes_text = []
        for ref in scene_refs:
            scenes_text.append({
                "scene_number": int(ref["scene_number"]),
                "description": (ref.get("description") or "")[:500],
                "has_reference_image": bool(ref.get("image_bytes")),
            })

        prompt = f"""
You are matching uploaded media files to scenes of a video production project.

Scenes in this project (ONLY these scene_number values are valid: {valid_numbers}):
{json.dumps(scenes_text, ensure_ascii=False, indent=2)}

For every scene that has a reference image, that image is attached below,
labeled "REFERENCE scene N". Each uploaded file's preview frame is attached
after that, labeled "UPLOAD <filename>".

The uploaded files are usually video clips generated FROM one of the
reference images, so the correct match will look like the SAME picture
(same character, composition, background) as one reference image. Visual
identity with a reference image is the strongest evidence - use scene
descriptions only when no reference image matches.

Rules:
- Use ONLY scene_number values from the valid list above.
- confidence "high"  : the upload clearly shows the same picture as that scene's reference image.
- confidence "medium": likely match but not visually certain (e.g. matched by description only).
- confidence "low"   : best guess.
- If an upload matches nothing at all, omit it from the output.

Respond STRICTLY as a single JSON object, no markdown, in this format:
{{
  "file1.mp4": {{"scene": 3, "confidence": "high"}},
  "file2.png": {{"scene": 1, "confidence": "medium"}}
}}
"""

        parts: List[Dict[str, Any]] = [{"text": prompt}]

        for ref in scene_refs:
            image_bytes = ref.get("image_bytes")
            if not image_bytes:
                continue
            small, mime = _downscale_to_jpeg(image_bytes)
            parts.append({"text": f"REFERENCE scene {int(ref['scene_number'])}"})
            parts.append({
                "inline_data": {
                    "mime_type": mime,
                    "data": base64.b64encode(small).decode("utf-8"),
                }
            })

        for filename, img_bytes, mime in uploaded_assets:
            small, small_mime = _downscale_to_jpeg(img_bytes)
            parts.append({"text": f"UPLOAD {filename}"})
            parts.append({
                "inline_data": {
                    "mime_type": small_mime,
                    "data": base64.b64encode(small).decode("utf-8"),
                }
            })

        # ---- Gemini 호출 ----------------------------------------------------
        try:
            url = f"{gemini_service.base_url}/models/gemini-2.5-flash:generateContent?key={gemini_service.api_key}"
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            }

            import httpx
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                response = await client.post(url, json=payload)
                result = response.json()

            if "candidates" not in result:
                print(f"[VideoMatcher] Failed response from Gemini: {result}")
                return {}

            text_resp = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            text_resp = re.sub(r"```json\s*", "", text_resp)
            text_resp = re.sub(r"\s*```", "", text_resp)
            mapping = json.loads(text_resp)

            clean_mapping: Dict[str, Dict[str, Any]] = {}
            valid_set = set(valid_numbers)
            for key, value in mapping.items():
                try:
                    if isinstance(value, dict):
                        scene = int(value.get("scene"))
                        confidence = str(value.get("confidence") or "medium").lower()
                    else:
                        scene = int(value)
                        confidence = "medium"
                    if confidence not in ("high", "medium", "low"):
                        confidence = "medium"
                    if scene in valid_set:
                        clean_mapping[key] = {"scene": scene, "confidence": confidence}
                except Exception:
                    continue
            return clean_mapping
        except Exception as e:
            print(f"[VideoMatcher] Error calling Gemini: {e}")
            return {}


video_matcher = VideoMatcher()
