import os
import json
import base64
import re
from typing import List, Dict, Any, Tuple
from moviepy.editor import VideoFileClip
from PIL import Image
import io

from services.gemini_service import gemini_service
import database as db

class VideoMatcher:
    @staticmethod
    def extract_middle_frame_bytes(video_path: str) -> bytes:
        """비디오 파일에서 중간 지점의 프레임 이미지를 PNG 바이트로 추출합니다."""
        clip = None
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            mid_time = duration / 2.0
            
            # 중간 시간대의 프레임 가져오기
            frame = clip.get_frame(mid_time)
            
            # PIL Image로 변환하여 PNG 바이트 배열로 저장
            img = Image.fromarray(frame)
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
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
        uploaded_assets: List[Tuple[str, bytes, str]] # List of (filename, file_bytes, mime_type)
    ) -> Dict[str, int]:
        """
        Gemini Vision을 사용하여 프로젝트의 각 씬 정보(대본 등)와 업로드된 에셋 목록을 매칭합니다.
        uploaded_assets에는 이미 비디오의 경우 추출된 프레임 이미지 바이트가 들어있을 수 있습니다.
        """
        # 1. 프로젝트의 씬 리스트 가져오기
        p_data = db.get_image_prompts(project_id)
        if not p_data:
            print(f"[VideoMatcher] No image prompts found for project {project_id}")
            return {}

        scenes_info = []
        for idx, item in enumerate(p_data):
            # 씬의 대사 및 프롬프트 정보 요약
            scene_text = item.get("scene_text") or item.get("scene") or item.get("prompt_ko") or ""
            prompt_en = item.get("prompt_en") or ""
            scenes_info.append({
                "scene_number": idx + 1,
                "scene_description": scene_text,
                "prompt_en": prompt_en
            })

        if not scenes_info:
            return {}

        # 2. Gemini API 호출을 위한 이미지 바이너리 페이로드 준비
        # Gemini-2.5-Flash 또는 gemini-3.1-flash-image-preview Multimodal 프롬프트 작성
        prompt = f"""
You are an expert AI Video Editor and Assistant.
Your task is to match the uploaded file previews (images representing scenes or frames of video) to the correct Scene Numbers of a video production project.

Here are the list of Scenes and their descriptions for this project:
{json.dumps(scenes_info, ensure_ascii=False, indent=2)}

Analyze each of the uploaded images carefully, and map them to the best-fitting Scene Number.
Some scenes might be missing files, and some files might map to the same scene, but try to find the absolute best 1-to-1 or N-to-1 match.

Respond STRICTLY in a JSON format. Do not write any markdown code blocks, do not write anything else.
The output format must be a single JSON object where keys are the original filenames, and values are the matched scene numbers (integers starting from 1).
Example output:
{{
  "file1.png": 1,
  "video2.mp4": 3
}}
"""

        # Gemini Multimodal API 페이로드 구성
        parts = [{"text": prompt}]
        for filename, img_bytes, mime in uploaded_assets:
            encoded = base64.b64encode(img_bytes).decode("utf-8")
            parts.append({"text": f"Filename: {filename}"})
            parts.append({
                "inline_data": {
                    "mime_type": "image/png", # 프레임 추출본이나 이미지는 PNG 형식으로 규격화
                    "data": encoded
                }
            })

        # Gemini 호출
        try:
            url = f"{gemini_service.base_url}/models/gemini-2.5-flash:generateContent?key={gemini_service.api_key}"
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json"
                }
            }

            import httpx
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                response = await client.post(url, json=payload)
                result = response.json()

                if "candidates" in result:
                    text_resp = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # Markdown code block wrapping 제거
                    text_resp = re.sub(r"```json\s*", "", text_resp)
                    text_resp = re.sub(r"\s*```", "", text_resp)
                    
                    mapping = json.loads(text_resp)
                    # 정수형태 확인 및 보정
                    clean_mapping = {}
                    for k, v in mapping.items():
                        try:
                            clean_mapping[k] = int(v)
                        except Exception:
                            pass
                    return clean_mapping
                else:
                    print(f"[VideoMatcher] Failed response from Gemini: {result}")
                    return {}
        except Exception as e:
            print(f"[VideoMatcher] Error calling Gemini: {e}")
            return {}

video_matcher = VideoMatcher()
