import os
import time
import json
import hashlib
import tempfile
import httpx
from services.web_admin_client import web_admin_client
from google import genai
from config import config

# Note: BackgroundTasks may lose tasks if the server restarts.
# In Phase 2.5, this will be migrated to a robust job queue (e.g., Celery/RQ/Supabase Jobs).

PROMPT = """Analyze this voice sample and estimate the following traits. 
The traits should be scored from 0 to 100.
Return ONLY valid JSON format. Do not use markdown blocks.
Required traits: warmth, authority, storytelling, drama, education, luxury, comedy, cute, news, romance.
Also estimate the language code (e.g., "en", "ko", "ja").

Output format exactly:
{
    "voice_traits": {
        "warmth": 0,
        "authority": 0,
        "storytelling": 0,
        "drama": 0,
        "education": 0,
        "luxury": 0,
        "comedy": 0,
        "cute": 0,
        "news": 0,
        "romance": 0
    },
    "language": "en"
}
"""

async def analyze_voice_task(voice_id: str, audio_url: str):
    # 1. Update status to analyzing
    _update_status(voice_id, "analyzing")
    
    temp_path = None
    try:
        # 2. Download sample_audio_url
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(audio_url)
            if resp.status_code != 200:
                raise Exception(f"Failed to download audio, status {resp.status_code}")
                
            audio_bytes = resp.content
            if len(audio_bytes) == 0:
                raise Exception("Downloaded file is empty")
                
        # 3. Temp file save
        ext = audio_url.split('.')[-1][:4] if '.' in audio_url else 'mp3'
        temp_fd, temp_path = tempfile.mkstemp(suffix=f".{ext}")
        with os.fdopen(temp_fd, 'wb') as f:
            f.write(audio_bytes)
            
        # 4. Hash generation
        sample_hash = hashlib.sha256(audio_bytes).hexdigest()
        
        # 5. Duration measurement
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            sample_duration = round(float(result.stdout.strip()), 2)
        except Exception as e:
            raise Exception(f"Duration measurement failed (ffmpeg/ffprobe may be missing): {e}")

        # 6. Gemini Audio Analysis
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        
        try:
            # Upload file to Gemini
            uploaded_file = client.files.upload(file=temp_path)
            
            # Request generation
            # Let's wait a moment for processing if needed, though audio is usually fast
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    uploaded_file,
                    PROMPT
                ]
            )
            raw_result = response.text
            client.files.delete(name=uploaded_file.name)
        except Exception as e:
            raise Exception(f"Gemini API failed: {e}")
            
        # Parse JSON
        try:
            import re
            json_match = re.search(r'\{.*\}', raw_result, re.DOTALL)
            if not json_match:
                raise Exception("No JSON block found")
            parsed = json.loads(json_match.group(0))
            traits = parsed.get("voice_traits", {})
            language = parsed.get("language", "unknown")
            
            # Simple validation
            if not isinstance(traits, dict) or "warmth" not in traits:
                raise Exception("Invalid JSON structure returned by Gemini")
                
        except Exception as e:
            raise Exception(f"JSON Parsing failed: {e} | Raw: {raw_result[:200]}")
            
        # 7-12. Update Supabase
        analysis_result = {
            "error": False,
            "stage": "complete",
            "timestamp": time.time(),
            "raw_response": raw_result
        }
        
        update_payload = {
            "sample_duration": sample_duration,
            "sample_language": language,
            "sample_hash": sample_hash,
            "voice_traits": traits,
            "analysis_result": analysis_result,
            "analysis_status": "analyzed"
        }
        
        # Check confidence (mock heuristic: if we got traits, maybe it's fine, but let's check max value)
        max_trait = max(traits.values()) if traits else 0
        if max_trait < 10:
            update_payload["analysis_status"] = "needs_review"
            
        _update_record(voice_id, update_payload)

    except Exception as e:
        # Failure
        err_msg = str(e)
        stage = "unknown"
        if "download" in err_msg.lower() or "empty" in err_msg.lower(): stage = "download"
        elif "Duration" in err_msg: stage = "duration"
        elif "Gemini" in err_msg: stage = "gemini_analysis"
        elif "JSON" in err_msg: stage = "json_parse"
        
        analysis_result = {
            "error": True,
            "stage": stage,
            "message": err_msg,
            "timestamp": time.time()
        }
        
        try:
            _update_record(voice_id, {
                "analysis_status": "failed",
                "analysis_result": analysis_result
            })
        except:
            pass # Last resort
            
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


def _update_status(voice_id: str, status: str):
    try:
        web_admin_client.supabase_patch("voice_profiles", {"analysis_status": status}, id=f"eq.{voice_id}")
    except Exception as e:
        print(f"Failed to update status to {status} for {voice_id}: {e}")

def _update_record(voice_id: str, payload: dict):
    try:
        web_admin_client.supabase_patch("voice_profiles", payload, id=f"eq.{voice_id}")
    except Exception as e:
        raise Exception(f"Supabase update failed: {e}")
