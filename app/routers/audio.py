from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
import time
import database as db
from config import config
from services.replicate_service import replicate_service
from services.gemini_service import gemini_service

router = APIRouter(prefix="/api/audio", tags=["Audio"])

class AudioGenRequest(BaseModel):
    project_id: int
    scene_number: int
    type: str  # "sfx" or "bgm"
    prompt: str
    duration: int = 5

@router.post("/generate")
async def generate_audio(req: AudioGenRequest):
    """Generate SFX or BGM via Replicate"""
    try:
        # Check project
        project = db.get_project(req.project_id)
        if not project: raise HTTPException(404, "Project not found")

        # Output path setup
        output_dir = os.path.join(config.OUTPUT_DIR, str(req.project_id), "assets", "audio")
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = int(time.time())
        filename = f"{req.type}_scene_{req.scene_number}_{timestamp}.{ 'mp3' if req.type=='bgm' else 'wav' }" # Replicate output format varies, usually mp3 or wav
        # Actually Replicate output is usually WAV or MP3 depending on model. 
        # MusicGen -> WAV/MP3? AudioLDM -> WAV.
        
        # Call Service
        audio_data = None
        if req.type == "sfx":
            audio_data = await replicate_service.generate_sfx(req.prompt, req.duration)
        elif req.type == "bgm":
            audio_data = await replicate_service.generate_music(req.prompt, req.duration)
        else:
            raise HTTPException(400, "Invalid type. Use 'sfx' or 'bgm'")
            
        if not audio_data:
            raise HTTPException(500, "Audio generation failed (no data returned)")

        # Save File
        file_path = os.path.join(output_dir, filename)
        with open(file_path, "wb") as f:
            f.write(audio_data)
            
        # Web URL
        audio_url = f"/output/{req.project_id}/assets/audio/{filename}"
        
        # Update DB
        conn = db.get_db()
        cur = conn.cursor()
        if req.type == "sfx":
            cur.execute("UPDATE image_prompts SET sfx_url = ? WHERE project_id = ? AND scene_number = ?", (audio_url, req.project_id, req.scene_number))
        else:
            cur.execute("UPDATE image_prompts SET bgm_url = ? WHERE project_id = ? AND scene_number = ?", (audio_url, req.project_id, req.scene_number))
        conn.commit()
        conn.close()
        
        return {"status": "success", "audio_url": audio_url}

    except Exception as e:
        print(f"Audio Gen Error: {e}")
        raise HTTPException(500, str(e))

class AudioAnalyzeRequest(BaseModel):
    project_id: int

@router.post("/analyze-scenes")
async def analyze_audio_prompts(req: AudioAnalyzeRequest):
    """Use Gemini to suggest SFX/BGM prompts for all scenes"""
    try:
        # 1. Get Script/Scenes
        prompts = db.get_image_prompts(req.project_id)
        if not prompts: raise HTTPException(400, "No scenes found. Generate image prompts first.")
        
        # Prepare context for Gemini
        scene_texts = []
        for p in prompts:
            scene_texts.append(f"Scene {p['scene_number']}: {p['scene_text']} (Visual: {p['prompt_en']})")
            
        full_context = "\n".join(scene_texts)
        
        # 2. Call Gemini
        # We need a strict JSON response
        system_prompt = """
        You are an expert Audio Director for a video production.
        Analyze the following scenes and suggest audio prompts for SFX (Sound Effects) and BGM (Background Music) for EACH scene.
        
        Output strictly in JSON format:
        {
            "scenes": [
                {
                    "scene_number": 1,
                    "sfx_prompt": "footsteps on gravel, birds chirping",
                    "bgm_prompt": "suspenseful ambient drone, low frequency"
                },
                ...
            ]
        }
        
        Rules:
        - sfx_prompt: specific sounds visible or implied in the scene.
        - bgm_prompt: mood, instruments, tempo.
        - If no SFX needed, use "silence".
        """
        
        print(f"🎵 Analyzing Audio for Project {req.project_id}...")
        
        # [FIX] gemini_service.generate_text does not support system_prompt arg. Combine them.
        combined_prompt = f"{system_prompt}\n\n[SCENES TO ANALYZE]\n{full_context}"
        response = await gemini_service.generate_text(combined_prompt)
        
        # Parse JSON
        import json
        try:
            # Clean md blocks
            cleaned = response.replace("```json", "").replace("```", "").strip()
            data = json.loads(cleaned)
            analysis = data.get("scenes", [])
        except:
            print(f"JSON Parse Error: {response}")
            raise HTTPException(500, "Failed to parse AI response")
            
        # 3. Save to DB
        conn = db.get_db()
        cur = conn.cursor()
        
        for item in analysis:
            s_num = item.get('scene_number')
            sfx = item.get('sfx_prompt')
            bgm = item.get('bgm_prompt')
            
            cur.execute("""
                UPDATE image_prompts 
                SET sfx_prompt = ?, bgm_prompt = ?
                WHERE project_id = ? AND scene_number = ?
            """, (sfx, bgm, req.project_id, s_num))
            
        conn.commit()
        conn.close()

        return {"status": "success", "count": len(analysis)}

    except Exception as e:
        print(f"Audio Analysis Error: {e}")
        raise HTTPException(500, str(e))

class AudioPromptUpdate(BaseModel):
    project_id: int
    scene_number: int
    sfx_prompt: Optional[str] = None
    bgm_prompt: Optional[str] = None

@router.post("/update-prompt")
async def update_audio_prompt(req: AudioPromptUpdate):
    try:
        conn = db.get_db()
        cur = conn.cursor()
        
        if req.sfx_prompt is not None:
            cur.execute("UPDATE image_prompts SET sfx_prompt = ? WHERE project_id = ? AND scene_number = ?", (req.sfx_prompt, req.project_id, req.scene_number))
        
        if req.bgm_prompt is not None:
            cur.execute("UPDATE image_prompts SET bgm_prompt = ? WHERE project_id = ? AND scene_number = ?", (req.bgm_prompt, req.project_id, req.scene_number))
            
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(500, str(e))


# =====================================================
# [NEW] BGM/SFX 파일 업로드 API
# POST /api/upload-audio
# =====================================================
from fastapi import UploadFile, File, Form

@router.post("/upload-audio", include_in_schema=True)
async def upload_audio_file(
    file: UploadFile = File(...),
    project_id: int = Form(...),
    type: str = Form("bgm")   # "bgm" or "sfx"
):
    """
    BGM/SFX 파일을 서버에 업로드하고 웹 URL을 반환합니다.
    """
    try:
        # 저장 디렉터리
        save_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "audio")
        os.makedirs(save_dir, exist_ok=True)

        # 안전한 파일명 생성
        ext = os.path.splitext(file.filename)[1].lower() or ".mp3"
        safe_name = f"{type}_{int(time.time())}{ext}"
        save_path = os.path.join(save_dir, safe_name)

        # 파일 저장
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        # 웹 URL 계산
        rel_path = os.path.relpath(save_path, config.OUTPUT_DIR).replace("\\", "/")
        web_url = f"/output/{rel_path}"

        print(f"✅ [Audio Upload] {type} saved: {save_path}")
        return {"status": "success", "url": web_url, "filename": safe_name}

    except Exception as e:
        print(f"❌ [Audio Upload] Error: {e}")
        raise HTTPException(500, str(e))


# =====================================================
# [NEW] 프로젝트의 BGM/SFX 파일 목록 조회
# GET /api/projects/{project_id}/audio-assets
# =====================================================
from fastapi import Path as PathParam

@router.get("/projects/{project_id}/audio-assets")
async def get_audio_assets(project_id: int):
    """
    프로젝트에 저장된 BGM/SFX 파일 목록을 반환합니다.
    audio_gen 등에서 생성된 파일들도 포함됩니다.
    """
    try:
        bgm_files = []
        sfx_files = []

        # 1. 업로드된 파일 (assets/audio/)
        asset_dir = os.path.join(config.OUTPUT_DIR, str(project_id), "assets", "audio")
        if os.path.isdir(asset_dir):
            for fname in os.listdir(asset_dir):
                if fname.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg', '.flac')):
                    rel = os.path.relpath(
                        os.path.join(asset_dir, fname), config.OUTPUT_DIR
                    ).replace("\\", "/")
                    url = f"/output/{rel}"
                    item = {"name": fname, "url": url}
                    if fname.startswith("bgm"):
                        bgm_files.append(item)
                    else:
                        sfx_files.append(item)

        # 2. DB의 audio_gen에서 생성된 파일들 (bgm_url 컬럼)
        try:
            conn = db.get_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT scene_number, bgm_url FROM image_prompts WHERE project_id = ? AND bgm_url IS NOT NULL AND bgm_url != ''",
                (project_id,)
            )
            rows = cur.fetchall()
            conn.close()
            for row in rows:
                url = row['bgm_url'] if row['bgm_url'].startswith('/') else f"/output/{row['bgm_url']}"
                bgm_files.append({
                    "name": f"씬 {row['scene_number']} BGM",
                    "url": url
                })
        except Exception as e:
            print(f"[audio-assets] DB query error: {e}")

        return {"status": "ok", "bgm_files": bgm_files, "sfx_files": sfx_files}

    except Exception as e:
        raise HTTPException(500, str(e))

