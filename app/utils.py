"""
공유 유틸리티 — 여러 라우터에서 공통으로 사용하는 헬퍼/상수/딕셔너리
"""

STYLE_PROMPTS = {
    "realistic": "A highly realistic photo, 8k resolution, highly detailed photography, lifelike textures, natural lighting, professional cinematography, high quality",
    "anime": "Anime style illustration, vibrant colors, detailed background, Makoto Shinkai style, high quality",
    "cinematic": "Cinematic movie shot, dramatic lighting, shadow and light depth, highly detailed, 4k",
    "minimal": "Minimalist flat vector illustration, simple shapes, clean lines, white background, high quality",
    "3d": "3D render, Pixar style, soft studio lighting, octane render, 4k, high quality",
    "k_webtoon": "Modern K-webtoon manhwa style, high-quality digital illustration, sharp line art, vibrant colors, expressive character, modern manhwa aesthetic, professional digital art, no text, no speech bubbles",
    "ghibli": "Studio Ghibli style, cel shaded, vibrant colors, lush background, Hayao Miyazaki style, highly detailed, masterfully painted",
    "k_manhwa": "A clean, high-quality, full-color webtoon style illustration in a 16:9 cinematic aspect ratio. Bold black outlines, flat graphic colors with soft gradients, clean vector-like finish. Isolated on a fully illustrated 16:9 detailed background. A cute, minimalist cartoon character with a perfectly uniform white circular head (solid white surface, no hair, shiny bald). THE FACE MUST HAVE a pair of distinct black eyes and a simple mouth. THE CHARACTER HAS EXACTLY TWO ARMS (one left arm, one right arm) AND EXACTLY TWO WHITE GLOVED HANDS TOTAL. NO THIRD ARM, NO FOURTH ARM, NO MULTIPLE LIMBS. NO REAR ARMS. The black limbs must have a perfectly uniform and consistent thickness. The character always wears a long-sleeved hooded sweatshirt (hoodie) that covers the arms down to the wrists, the hoodie is vibrant teal-blue (Brand Color: #00ADB5), black pants and simple sneakers. IMPORTANT: Background elements and other illustrated characters MUST NEVER overlap, touch, or be attached to the main character. The main character must be clearly separated from the background layers. ABSOLUTELY NO TEXT. NO HAIR. ONLY TWO ARMS AND TWO HANDS TOTAL. NO EXTRA LIMBS."
}
import os
import re
import datetime
from fastapi import HTTPException, UploadFile

import database as db
import config

# ============ 파일 업로드 검증 헬퍼 ============
ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".ogg", ".aac", ".m4a", ".flac"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_AUDIO_SIZE = 100 * 1024 * 1024   # 100 MB
MAX_VIDEO_SIZE = 500 * 1024 * 1024   # 500 MB
MAX_IMAGE_SIZE =  20 * 1024 * 1024   # 20 MB


def validate_upload(file: UploadFile, allowed_exts: set, max_bytes: int):
    """파일 확장자·크기 검증. 문제 시 HTTPException 발생."""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"허용되지 않는 파일 형식입니다: {ext or '(없음)'}. 허용: {', '.join(sorted(allowed_exts))}")
    safe_name = os.path.basename(filename)
    if safe_name != filename.replace("\\", "/").split("/")[-1]:
        raise HTTPException(400, "잘못된 파일 이름입니다.")
    return ext, safe_name


def get_project_output_dir(project_id: int):
    """
    프로젝트 ID를 기반으로 '프로젝트명_날짜' 형식의 폴더를 생성하고 경로를 반환합니다.
    Returns: (abs_path, web_path)
    """
    project = db.get_project(project_id)
    if not project:
        return config.OUTPUT_DIR, "/output"

    safe_name = re.sub(r'[\\/*?:"<>|]', "", project['name']).strip()
    safe_name = re.sub(r'\s+', '_', safe_name)

    today = datetime.datetime.now().strftime("%Y%m%d")
    folder_name = f"{safe_name}_{today}"

    abs_path = os.path.join(config.OUTPUT_DIR, folder_name)
    os.makedirs(abs_path, exist_ok=True)

    web_path = f"/output/{folder_name}"
    return abs_path, web_path
