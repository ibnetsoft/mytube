"""
TTS API Router
"""
import asyncio
import json
import os
import re
import time

import httpx
from fastapi import APIRouter, HTTPException, Form

from config import config
import database as db
from app.models.media import TTSRequest
from app.utils import get_project_output_dir
from services.web_admin_client import web_admin_client

router = APIRouter(prefix="/api", tags=["TTS"])


# ===========================================
# API: TTS
# ===========================================

@router.post("/tts/generate")
async def tts_generate(req: TTSRequest):
    """TTS 음성 생성"""
    import time
    from services.tts_service import tts_service

    start_time = time.time()
    tts_model_id = "multi-voice" if req.multi_voice else (req.voice_id or "default")

    def _log_tts(status: str, error_msg: str = ""):
        try:
            db.add_ai_log(
                req.project_id, "tts", tts_model_id, req.provider, status,
                prompt_summary=(req.text or "")[:100],
                error_msg=error_msg,
                elapsed_time=time.time() - start_time,
            )
        except Exception as log_e:
            print(f"[TTS] Failed to write ai_log: {log_e}")

    now_kst = config.get_kst_time()
    from services.tts_service import language_code_for_tts
    if req.project_id and (not req.language or req.language == "ko-KR"):
        try:
            project = db.get_project(req.project_id) or {}
            settings = db.get_project_settings(req.project_id) or {}
            project_lang = settings.get("target_language") or project.get("language")
            if project_lang:
                req.language = language_code_for_tts(project_lang)
        except Exception as lang_e:
            print(f"[TTS] Language fallback warning: {lang_e}")

    # Provider별 확장자 설정
    # [FIX] Gemini는 현재 EdgeTTS(mp3)로 fallback되므로 mp3 사용
    ext = "mp3" # "wav" if req.provider == "gemini" else "mp3"
    filename = f"tts_{now_kst.strftime('%Y%m%d_%H%M%S')}.{ext}"

    output_path = None # 초기화
    
    # 프로젝트 ID가 있으면 전용 폴더 사용
    if req.project_id:
        output_dir, web_dir = get_project_output_dir(req.project_id)
        # 서비스(tts_service)가 output_dir를 동적으로 받아야 함.
        # 하지만 tts_service는 init에서 output_dir를 고정함.
        # 파일명에 절대 경로를 넘겨주면 os.path.join에서 무시되는 특성을 이용하거나,
        # 서비스를 수정해야 함. 
        # tts_service의 메서드들이 filename만 받고 내부에서 join함.
        # -> tts_service 메서드 호출 시 filename 인자에 '절대 경로'를 넘기면
        # os.path.join(base, absolute) -> absolute가 됨 (Windows/Linux 공통)
        # 테스트 필요하지만 Python os.path.join 스펙상 두번째 인자가 절대경로면 앞부분 무시됨.
        # 따라서 filename에 full path를 넘기면 됨.
        result_filename = os.path.normpath(os.path.abspath(os.path.join(output_dir, filename)))
    else:
        # Fallback
        output_dir = config.OUTPUT_DIR
        web_dir = "/output"
        result_filename = os.path.normpath(os.path.abspath(os.path.join(config.OUTPUT_DIR, filename)))

    # ElevenLabs 전용 상세 보이스 설정 구성
    el_voice_settings = {"speed": req.speed}
    if req.stability is not None:
        el_voice_settings["stability"] = req.stability
    if req.similarity_boost is not None:
        el_voice_settings["similarity_boost"] = req.similarity_boost
    if req.style is not None:
        el_voice_settings["style"] = req.style

        # ----------------------------------------------------------------
    try:
        # ----------------------------------------------------------------
        # 멀티 보이스 모드 처리
        # ----------------------------------------------------------------
        if req.multi_voice and req.voice_map:
            # 1. 텍스트 파싱 (Frontend와 동일한 로직: "이름: 대사")
            segments = []
            lines = req.text.split('\n')
            
            # 정규식: 화자 이름과 괄호 안의 감정 지문 캡처 (이름: 대사 형식 및 이름) 대사 형식 지원)
            pattern = re.compile(
                r'^\s*(?:'
                r'[\*\_\[\(]*([^\s:\[\(\*\_]+)[\*\_\]\)]*[ \t]*(\([^)]*\))?[ \t]*[:：][ \t]*(.*)'
                r'|'
                r'([^\s:\[\(\*\_]+)[ \t]*[\)）\]][ \t]*(.*)'
                r')$'
            )
            
            current_chunk = []
            current_speaker = None
            
            # 파일명을 위한 타임스탬프
            base_filename = os.path.splitext(filename)[0]
            
            # 라인별 파싱 및 그룹화
            for line in lines:
                match = pattern.match(line.strip())
                if match:
                    # 새로운 화자 등장 -> 이전 청크 저장
                    if current_chunk:
                        segments.append({
                            "speaker": current_speaker,
                            "text": "\n".join(current_chunk)
                        })
                    
                    if match.group(1) is not None:
                        current_speaker = match.group(1).strip()
                        emotion = match.group(2) or ""
                        content = match.group(3).strip()
                    else:
                        current_speaker = match.group(4).strip()
                        emotion = ""
                        content = match.group(5).strip()

                    # 백엔드에서도 화자 이름에서 특수기호 2차 정지
                    current_speaker = re.sub(r'[\*\_\#\[\]\(\)]', '', current_speaker).strip()
                    
                    if emotion:
                        content = f"{emotion} {content}"
                    current_chunk = [content]
                else:
                    # 화자 없음 -> 이전 화자에 이어서 추가 (없으면 default)
                    current_chunk.append(line.strip())
            
            # 마지막 청크 처리
            if current_chunk:
                segments.append({
                    "speaker": current_speaker,
                    "text": "\n".join(current_chunk)
                })

            print(f"🎙️ [DEBUG MULTIVOICE] Parsed segments: {[{'speaker': s['speaker'], 'text': s['text'][:30]} for s in segments]}")

            # 2. 세그먼트별 오디오 생성 (동시 생성 개수 제한)
            # ElevenLabs eleven_v3는 동시 요청 2개 제한이 있으므로 Semaphore=2
            semaphore = asyncio.Semaphore(2) # 최대 2개 동시 요청 (eleven_v3 동시성 제한 방지)
            
            async def process_segment(idx, segment):
                async with semaphore:
                    speaker = segment["speaker"]
                    seg_text = segment["text"]
                    
                    # 15,000자 대본의 경우 수백 개의 세그먼트가 나올 수 있으므로 로그 출력
                    if idx % 5 == 0 or idx == len(segments) - 1:
                        print(f"🎙️ [Main] TTS 세그먼트 생성 중... ({idx+1}/{len(segments)})")
                    
                    # 화자별 목소리 결정
                    target_voice = req.voice_map.get(speaker, req.voice_id)
                    if isinstance(target_voice, dict) and "id" in target_voice:
                        target_voice = target_voice["id"]
                    
                    provider = req.provider
                    # [ROBUSTNESS] '기본 설정 따름' 등의 비어있는 값 처리
                    if not target_voice:
                        target_voice = req.voice_id
                    
                    print(f"🎙️ [DEBUG MULTIVOICE] Segment {idx} (Speaker: '{speaker}') mapped to target_voice: '{target_voice}' (from voice_map: {req.voice_map}, fallback: '{req.voice_id}')")
                    
                    seg_filename = f"{base_filename}_seg_{idx:03d}.mp3"
                    seg_path = os.path.join(output_dir, seg_filename)
                    
                    try:
                        if provider == "elevenlabs":
                             result = await tts_service.generate_elevenlabs(seg_text, target_voice, seg_path, voice_settings=el_voice_settings)
                             # 실제 저장된 경로 검증 (None 또는 파일 없으면 실패 처리)
                             actual_path = result.get("audio_path") if result else None
                             if actual_path and os.path.exists(actual_path) and os.path.getsize(actual_path) > 0:
                                 return actual_path
                             else:
                                 print(f"❌ Segment {idx} (Speaker: {speaker}) - 파일 생성 실패 또는 빈 파일: {actual_path}")
                                 return None
                        elif provider == "openai":
                             await tts_service.generate_openai(seg_text, target_voice, "tts-1", seg_path, req.speed)
                             return seg_path if os.path.exists(seg_path) else None
                        else: # gemini / edge_tts
                             await tts_service.generate_gemini(seg_text, target_voice, req.language, req.style_prompt, seg_path, req.speed)
                             return seg_path if os.path.exists(seg_path) else None
                    except Exception as e:
                        print(f"❌ Segment {idx} (Speaker: {speaker}) generation failed: {e}")
                        return None

            print(f"🎙️ [Main] 멀티보이스 TTS 병렬 생성 시작 (총 {len(segments)}개, 동시 10개 제한)...")
            print(f"DEBUG: Voice Map: {req.voice_map}")
            segment_tasks = [process_segment(i, s) for i, s in enumerate(segments)]
            audio_files = [f for f in await asyncio.gather(*segment_tasks) if f]
            
            # 3. 오디오 합치기
            if audio_files:
                print(f"🔄 [Main] 오디오 파일 병합 시작 ({len(audio_files)}개)...")
                output_path = None
                
                # Blocking IO/Processing을 ThreadPool에서 실행
                loop = asyncio.get_event_loop()
                
                def merge_audio_sync():
                    nonlocal output_path
                    # 1. Try Pydub (Faster, no re-encode usually)
                    try:
                        from pydub import AudioSegment
                        import imageio_ffmpeg
                        
                        # ffmpeg 경로 명시적 설정 (Windows WinError 2 방지)
                        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                        AudioSegment.converter = ffmpeg_exe
                        # AudioSegment.ffmpeg = ffmpeg_exe # 일부 버전 호환성
                        
                        # [Robustness] ffprobe check disabled or assumed optional for simple concat?
                        # Pydub uses info_json which requires ffprobe.
                        # If imageio_ffmpeg doesn't provide ffprobe, pydub fails on from_file.
                        # We can try to skip pydub if we suspect ffprobe is missing, 
                        # but let's try it and catch exception.
                        
                        combined = AudioSegment.empty()
                        for af in audio_files:
                            combined += AudioSegment.from_file(af)
                        
                        combined.export(result_filename, format="mp3")
                        output_path = result_filename
                        print(f"✅ [Main] pydub으로 오디오 병합 완료: {result_filename}")
                        return True
                    except Exception as pydub_err:
                        # WinError 2 often means ffprobe missing
                        print(f"⚠️ pydub 병합 실패 ({pydub_err}), MoviePy로 재시도합니다.")
                        return False

                # Run Pydub in thread
                pydub_success = await loop.run_in_executor(None, merge_audio_sync)
                
                if pydub_success:
                    pass # Done
                else:
                    # 2. Key Fallback: MoviePy (Re-encodes, slower but reliable with imageio)
                    def merge_moviepy_sync():
                        nonlocal output_path
                        try:
                            from moviepy import AudioFileClip, concatenate_audioclips
                        except ImportError:
                            from moviepy.audio.io.AudioFileClip import AudioFileClip
                            from moviepy.audio.AudioClip import concatenate_audioclips
                        
                        clips = []
                        try:
                            for af in audio_files:
                                try:
                                    clips.append(AudioFileClip(af))
                                except Exception as e:
                                    print(f"Failed to load clip {af}: {e}")
                            
                            if clips:
                                final_clip = concatenate_audioclips(clips)
                                # Modern MoviePy does not accept 'verbose' parameter. logger=None is sufficient.
                                final_clip.write_audiofile(result_filename, codec='libmp3lame', logger=None)
                                final_clip.close()
                                for clip in clips: clip.close()
                                output_path = result_filename
                                print(f"✅ [Main] MoviePy로 오디오 병합 완료: {result_filename}")
                                return True
                            else:
                                print(f"❌ [Main] MoviePy: No valid clips to merge.")
                                return False
                        except Exception as e:
                            print(f"❌ [Main] MoviePy 병합 실패: {e}")
                            return False
                            
                    moviepy_success = await loop.run_in_executor(None, merge_moviepy_sync)
                
                if output_path:
                    # 임시 파일 삭제
                    for af in audio_files:
                         try: os.remove(af)
                         except Exception: pass
                else:
                    error_msg = "오디오 병합 실패 (Pydub 및 MoviePy 모두 실패)"
                    _log_tts("failed", error_msg)
                    return {"status": "error", "error": error_msg}
            else:
                 error_msg = "생성된 오디오 세그먼트가 없습니다."
                 _log_tts("failed", error_msg)
                 return {"status": "error", "error": error_msg}

        # ----------------------------------------------------------------
        # 일반(단일) 모드 처리
        # ----------------------------------------------------------------
        else:
            # 1. ElevenLabs
            if req.provider == "elevenlabs":
                result = await tts_service.generate_elevenlabs(
                    req.text, req.voice_id, result_filename, voice_settings=el_voice_settings
                )
                # ElevenLabs returns a dict containing metadata
                if isinstance(result, dict):
                    output_path = result.get("audio_path")
                else:
                    output_path = result
            # 2. Google Cloud
            elif req.provider == "google_cloud":
                output_path = await tts_service.generate_google_cloud(
                    req.text, req.voice_id, req.language, result_filename, req.speed
                )
            # 3. Gemini
            elif req.provider == "gemini":
                output_path = await tts_service.generate_gemini(
                    req.text, req.voice_id, req.language, req.style_prompt, result_filename, req.speed
                )
            # 4. OpenAI
            elif req.provider == "openai":
                output_path = await tts_service.generate_openai(
                    req.text, req.voice_id, "tts-1", result_filename, req.speed
                )
            # 5. gTTS (Default)
            else:
                output_path = await tts_service.generate_gtts(
                    req.text, language_code_for_tts(req.language, "gtts"), result_filename
                )

        # 공통: DB 저장 및 리턴 처리
        # DB 저장 (프로젝트와 연결)
        if req.project_id:
             try:
                 # [FIX] Calculate actual duration before saving
                 duration = 0.0
                 try:
                     # Check file existence first
                     if os.path.exists(output_path):
                         # Try pydub first (more accurate for VBR/altered speed)
                         try:
                             import pydub
                             audio_seg = pydub.AudioSegment.from_file(output_path)
                             duration = audio_seg.duration_seconds
                         except ImportError:
                             # Fallback to MoviePy
                             try:
                                 from moviepy import AudioFileClip
                                 with AudioFileClip(output_path) as ac:
                                     duration = ac.duration
                             except Exception: pass
                         except Exception as e:
                             print(f"pydub check failed: {e}")
                             # Fallback to MoviePy
                             try:
                                 from moviepy import AudioFileClip
                                 with AudioFileClip(output_path) as ac:
                                     duration = ac.duration
                             except Exception: pass
                 except Exception as e:
                     print(f"Failed to calculate audio duration: {e}")

                 # [FIX] Logic for voice_id/name: Single voice should use actual ID
                 final_voice_id = "multi-voice" if req.multi_voice else (req.voice_id or "default")
                 final_voice_name = "Multi Voice" if req.multi_voice else (req.voice_id or "default")

                 db.save_tts(
                     req.project_id,
                     final_voice_id,
                     final_voice_name,
                     output_path,
                     duration
                 )
                 
                 # [FIX] Save script text to project settings
                 if req.text:
                     db.update_project_setting(req.project_id, "script", req.text)
                     print(f"DEBUG: Saved TTS text to project settings (len={len(req.text)})")

             except Exception as db_e:
                 print(f"TTS DB 저장 실패: {db_e}")
                 # Don't swallow! Raise or return error so frontend knows.
                 raise db_e
        
        # URL 생성
        if req.project_id:
            final_url = f"{web_dir}/{filename}"
        else:
            final_url = f"/output/{filename}"

        _log_tts("success")
        return {
            "status": "ok",
            "file": filename,
            "url": final_url,
            "full_path": output_path
        }

    except Exception as e:
        _log_tts("failed", str(e))
        return {"status": "error", "error": str(e)}


@router.get("/tts/voices")
async def tts_voices():
    """사용 가능한 TTS 음성 목록"""
    from services.tts_service import tts_service

    voices = []

    # Gemini
    try:
        gemini_voices = tts_service.get_gemini_voices()
        for v in gemini_voices:
            voices.append({
                "id": v,
                "name": f"Gemini - {v}",
                "provider": "gemini"
            })
    except Exception:
        pass

    # ElevenLabs
    if config.ELEVENLABS_API_KEY:
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                response = await client.get(
                    "https://api.elevenlabs.io/v1/voices",
                    headers={"xi-api-key": config.ELEVENLABS_API_KEY}
                )
                if response.status_code == 200:
                    data = response.json()
                    for v in data.get("voices", []):
                        voices.append({
                            "voice_id": v["voice_id"],
                            "name": v["name"],
                            "provider": "elevenlabs",
                            "preview_url": v.get("preview_url"),
                            "labels": v.get("labels", {})
                        })
        except Exception:
            pass

    # [NEW] 수동 등록한 커스텀 보이스 병합
    try:
        custom_voices = db.get_global_setting("custom_voices", [])
        if isinstance(custom_voices, list):
            merged_custom_voices = list(custom_voices)
        else:
            merged_custom_voices = []

        remote_settings = web_admin_client.fetch_global_setting_values(["custom_voices"])
        remote_custom_voices = remote_settings.get("custom_voices")
        if isinstance(remote_custom_voices, str):
            try:
                remote_custom_voices = json.loads(remote_custom_voices)
            except Exception:
                remote_custom_voices = []
        if isinstance(remote_custom_voices, list):
            by_id = {
                str(item.get("voice_id")): item
                for item in merged_custom_voices
                if isinstance(item, dict) and item.get("voice_id")
            }
            for item in remote_custom_voices:
                if isinstance(item, dict) and item.get("voice_id"):
                    by_id[str(item["voice_id"])] = item
            merged_custom_voices = list(by_id.values())

        existing_ids = {v.get("voice_id") for v in voices if v.get("provider") == "elevenlabs"}
        for cv in merged_custom_voices:
            vid = cv.get("voice_id")
            if vid and vid not in existing_ids:
                voices.append({
                    "voice_id": vid,
                    "name": f"{cv.get('name')} (커스텀)",
                    "provider": "elevenlabs",
                    "preview_url": None,
                    "labels": {"custom": "true"}
                })
    except Exception as e:
        print(f"[WARN] Failed to load custom voices from db: {e}")

    return {"voices": voices}


@router.post("/tts/voices/add")
async def add_elevenlabs_voice(
    name: str = Form(...),
    voice_id: str = Form(...)
):
    """ElevenLabs에 새 음성 등록 (Voice ID 수동 입력)"""
    name = name.strip()
    voice_id = voice_id.strip()
    
    if not name or not voice_id:
        raise HTTPException(status_code=400, detail="이름과 Voice ID는 필수 입력 항목입니다.")

    try:
        custom_voices = db.get_global_setting("custom_voices", [])
        if not isinstance(custom_voices, list):
            custom_voices = []

        # 중복 확인 및 업데이트
        exists = False
        for cv in custom_voices:
            if cv.get("voice_id") == voice_id:
                cv["name"] = name
                exists = True
                break
        
        if not exists:
            custom_voices.append({
                "voice_id": voice_id,
                "name": name,
                "provider": "elevenlabs"
            })
            
        db.save_global_setting("custom_voices", custom_voices)
        print(f"[SUCCESS] Custom Voice Registered: {name} (ID: {voice_id})")
        return {"status": "ok", "voice_id": voice_id, "name": name}
    except Exception as e:
        print(f"[WARN] Exception during voice registration: {e}")
        raise HTTPException(status_code=500, detail=str(e))
