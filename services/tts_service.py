"""
TTS (Text-to-Speech) 서비스
- ElevenLabs (유료, 고품질)
- Google Cloud TTS (유료, 고품질)
- gTTS (무료, Google 번역 기반)
"""
import httpx
import os
from typing import Optional
from dotenv import load_dotenv

from config import config

CONTENT_LANGUAGE_CONFIG = {
    "ko": {"gtts_lang": "ko", "google_lang": "ko-KR", "edge_voice": "ko-KR-SunHiNeural", "default_voice_name": "Puck"},
    "en": {"gtts_lang": "en", "google_lang": "en-US", "edge_voice": "en-US-JennyNeural", "default_voice_name": "Kore"},
    "ja": {"gtts_lang": "ja", "google_lang": "ja-JP", "edge_voice": "ja-JP-NanamiNeural", "default_voice_name": "Kore"},
}

ELEVENLABS_DEFAULT_VOICE_ID = "4JJwo477JUAx3HV0T7n7"


def normalize_content_language(value: str = None) -> str:
    lang = (str(value or "").strip().lower() or "ko")
    if lang.startswith("ko"):
        return "ko"
    if lang.startswith("en"):
        return "en"
    if lang.startswith("ja") or lang.startswith("jp"):
        return "ja"
    return "ko"


def language_code_for_tts(value: str = None, provider: str = "google") -> str:
    lang = normalize_content_language(value)
    config_key = "gtts_lang" if provider == "gtts" else "google_lang"
    return CONTENT_LANGUAGE_CONFIG[lang][config_key]


def edge_voice_for_language(value: str = None) -> str:
    lang = normalize_content_language(value)
    return CONTENT_LANGUAGE_CONFIG[lang]["edge_voice"]


def default_voice_name_for_language(value: str = None) -> str:
    lang = normalize_content_language(value)
    return CONTENT_LANGUAGE_CONFIG[lang]["default_voice_name"]

# gTTS
try:
    from gtts import gTTS
except ImportError:
    gTTS = None

# Google Cloud TTS
try:
    from google.cloud import texttospeech
except ImportError:
    texttospeech = None


try:
    try:
        from moviepy import AudioFileClip, concatenate_audioclips
    except ImportError:
        from moviepy.editor import AudioFileClip, concatenate_audioclips
except ImportError:
    try:
        from moviepy.audio.io.AudioFileClip import AudioFileClip
        from moviepy.audio.AudioClip import concatenate_audioclips
    except ImportError:
        AudioFileClip = None
        concatenate_audioclips = None


class TTSService:
    def __init__(self):
        self.elevenlabs_key = config.ELEVENLABS_API_KEY
        self.typecast_key = config.TYPECAST_API_KEY
        self.google_credentials = config.GOOGLE_APPLICATION_CREDENTIALS
        self.output_dir = config.OUTPUT_DIR
        
        # Google Cloud Client 초기화 (설정된 경우)
        if self.google_credentials and os.path.exists(self.google_credentials) and texttospeech:
            try:
                self.google_client = texttospeech.TextToSpeechClient.from_service_account_json(self.google_credentials)
            except Exception as e:
                print(f"Google TTS init warning: {e}")
                self.google_client = None
        else:
            self.google_client = None
            
        # OpenAI Client 초기화
        self.openai_client = None
        if config.OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
            except ImportError:
                print("OpenAI 라이브러리가 설치되지 않았습니다.")
            except Exception as e:
                print(f"OpenAI Client 초기화 실패: {e}")


    async def generate_sound_effect(self, text: str, duration_seconds: Optional[float] = None) -> Optional[bytes]:
        """ElevenLabs Sound Generation API를 사용하여 효과음 생성"""
        if not self.elevenlabs_key:
            print("ElevenLabs API Key missing")
            return None
            
        url = "https://api.elevenlabs.io/v1/sound-generation"
        headers = {
            "xi-api-key": self.elevenlabs_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
        }
        if duration_seconds:
            payload["duration_seconds"] = duration_seconds
        
        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    return response.content
                else:
                    print(f"ElevenLabs SFX Error: {response.text}")
                    return None
        except Exception as e:
            print(f"ElevenLabs SFX Exception: {e}")
            return None

    async def generate_elevenlabs(
        self,
        text: str,
        voice_id: str = "4JJwo477JUAx3HV0T7n7",
        filename: str = "tts_output.mp3",
        return_alignment: bool = True,
        voice_settings: Optional[dict] = None
    ) -> dict:
        """
        ElevenLabs TTS 생성 (with timestamps for subtitle alignment)
        
        Returns:
            dict: {
                "audio_path": str (파일 경로),
                "alignment": list (단어별 타이밍 정보),
                "duration": float (총 재생 시간)
            }
        """
        # [FIX] 텍스트 정제 (지문 제거 및 한국어 감정 괄호를 ElevenLabs용 영어 태그로 치환)
        import re
        
        EMOTION_MAP = {
            # --- Sad (슬픔) ---
            "슬프": "sad", "슬픈": "sad", "눈물": "sad", "울먹": "sad", "서글": "sad", "애절": "sad", "아련": "sad", 
            "씁쓸": "sad", "체념": "sad", "낙담": "sad", "외로운": "sad", "외롭게": "sad", "쓸쓸": "sad", 
            "떨리는": "sad", "애통": "sad", "비통": "sad", "절망": "sad", "우울": "sad", "괴로": "sad",
            
            # --- Quiet / Calm (차분함, 조용함, 덤덤함) ---
            "차분": "quietly", "조용": "quietly", "나직": "quietly", "잔잔": "quietly", "덤덤": "quietly", 
            "평온": "quietly", "나긋": "quietly", "낮게": "quietly", "낮은": "quietly", "속삭": "whispers",
            
            # --- Thoughtful / Serious / Cold (진지함, 무게감, 차가움) ---
            "진지": "thoughtful", "무게": "thoughtful", "차갑": "thoughtful", "냉정": "thoughtful", 
            "냉혹": "thoughtful", "단호": "thoughtful", "엄숙": "thoughtful", "설명": "thoughtful", 
            "강조": "thoughtful", "묵직": "thoughtful", "조심": "thoughtful", "어두운": "thoughtful", 
            "어둡게": "thoughtful", "경고": "thoughtful",
            
            # --- Happy / Exciting (기쁨, 흥분, 밝음) ---
            "기쁘": "happy", "기쁜": "happy", "신나": "excited", "활기": "excited", "즐겁": "happy", 
            "밝게": "happy", "밝은": "happy", "웃음": "happy", "웃으": "happy", "환희": "happy",
            "유쾌": "happy", "당차": "excited", "희망": "happy",
            
            # --- Angry (분노, 짜증, 분개) ---
            "화나": "angry", "분노": "angry", "적대": "angry", "짜증": "angry", "신경": "angry", 
            "윽박": "angry", "질책": "angry", "독설": "angry", "거칠": "angry", "울화": "angry",
            
            # --- Shout (크게 소리침) ---
            "소리": "shouts", "크게": "shouts", "외치": "shouts", "강하": "shouts", "질러": "shouts",
            
            # --- Pauses ---
            "쉬고": "pause", "pause": "pause", "정적": "long pause"
        }

        PHONETIC_MAP = {
            "한숨": "하아... ",
            "탄식": "하아... ",
            "하~": "하아... ",
            "휴~": "휴... ",
            "흡": "흡... ",
            "놀람": "앗... ",
            "경악": "앗... ",
        }
        
        def replace_ko_emotions(match):
            content = match.group(1).strip()
            
            # 1. Phonetic mapping
            phonetic_str = ""
            for ko_key, phonetic in PHONETIC_MAP.items():
                if ko_key in content:
                    phonetic_str = phonetic
                    break
                    
            # 2. Emotional tag
            emotion_tag = ""
            for ko_key, en_tag in EMOTION_MAP.items():
                if ko_key in content:
                    emotion_tag = f"[{en_tag}]"
                    break
            
            if emotion_tag or phonetic_str:
                return f"{emotion_tag} {phonetic_str}".strip()
            return "" # 매핑되지 않은 지문은 소리내어 읽지 않도록 제거
            
        text = re.sub(r'\(([^)]*)\)', replace_ko_emotions, text)
        text = self.clean_text(text)
        
        # [NEW] 문장 단위 분할 처리 (제한 10,000자, 안전빵 8,000자)
        max_chars = 8000
        if len(text) > max_chars:
            chunks = self._split_text(text, max_chars)
            print(f"DEBUG: Text too long ({len(text)} chars). Splitting into {len(chunks)} chunks for ElevenLabs.")
            
            chunk_files = []
            all_alignments = []
            cumulative_time = 0.0
            
            for i, chunk in enumerate(chunks):
                chunk_filename = f"temp_{i}_{filename}"
                result = await self.generate_elevenlabs(chunk, voice_id, chunk_filename, return_alignment, voice_settings)
                
                if result and result.get("audio_path"):
                    chunk_files.append(result["audio_path"])
                    
                    # 타이밍 정보 누적 (offset 보정)
                    if result.get("alignment"):
                        for item in result["alignment"]:
                            adjusted_item = item.copy()
                            adjusted_item["start"] = item["start"] + cumulative_time
                            adjusted_item["end"] = item["end"] + cumulative_time
                            all_alignments.append(adjusted_item)
                    
                    cumulative_time += result.get("duration", 0)
            
            if not chunk_files:
                return {"audio_path": None, "alignment": [], "duration": 0}
            
            output_path = os.path.join(self.output_dir, filename)
            self._merge_audio_files(chunk_files, output_path)
            
            # 타이밍 정보 저장
            alignment_path = output_path.replace(".mp3", "_alignment.json")
            import json
            with open(alignment_path, "w", encoding="utf-8") as f:
                json.dump(all_alignments, f, ensure_ascii=False, indent=2)
            
            return {
                "audio_path": output_path,
                "alignment": all_alignments,
                "duration": cumulative_time
            }

        # [FIX] 런타임에 .env 변경사항 반영
        load_dotenv(override=True)
        api_key = os.getenv("ELEVENLABS_API_KEY")
        
        if not api_key:
            raise ValueError("ElevenLabs API 키가 설정되지 않았습니다")

        # [NEW] with_timestamps 엔드포인트 사용
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"

        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }

        # [NEW] Voice Settings Override for Expressive Emotions
        final_settings = {
            "stability": 0.35,          # Lower stability (30-50%) allows voice to be much more emotional and natural
            "similarity_boost": 0.75,
            "style": 0.45               # Style Exaggeration (20-50%) amplifies the emotion tags
        }
        speed_factor = 1.0
        
        if voice_settings:
            final_settings["stability"] = float(voice_settings.get("stability", 0.35))
            final_settings["similarity_boost"] = float(voice_settings.get("similarity_boost", 0.75))
            final_settings["style"] = float(voice_settings.get("style", 0.45))
            speed_factor = float(voice_settings.get("speed", 1.0))

        # [NEW] Pre-prompting for emotional steering in ElevenLabs (English prompts are much more effective)
        PRE_PROMPT_MAP = {
            "sad": "In a very sad, sobbing, and crying voice, they say: ",
            "quietly": "In a very low, quiet, and calm whisper, they say: ",
            "whispers": "In a very low, quiet, and calm whisper, they say: ",
            "whispering": "In a very low, quiet, and calm whisper, they say: ",
            "thoughtful": "In a deep, serious, and thoughtful tone, they say: ",
            "happy": "In an extremely happy, cheerful, and laughing voice, they say: ",
            "excited": "In an extremely excited, high-pitched, and joyful voice, they say: ",
            "annoyed": "In a very annoyed, irritated, and impatient voice, they say: ",
            "angry": "In an extremely angry, furious, and harsh voice, they say: ",
            "shouting": "Yelling loudly in a very high-pitched and intense voice, they say: ",
            "shouts": "Yelling loudly in a very high-pitched and intense voice, they say: ",
        }
        
        # Check if the text contains any of these tags
        emotion_tag_match = re.search(r'\[([a-zA-Z\s]+)\]', text)
        has_emotion_prompt = False
        prompt_text = ""
        cleaned_text = text
        
        if emotion_tag_match:
            tag_content = emotion_tag_match.group(1).lower().strip()
            if tag_content in PRE_PROMPT_MAP:
                prompt_text = PRE_PROMPT_MAP[tag_content]
                # Remove the tag from the text sent to ElevenLabs to prevent reading it/confusion
                cleaned_text = text.replace(emotion_tag_match.group(0), "").strip()
                has_emotion_prompt = True
                print(f"[EMOTION] [ElevenLabs TTS] Detected emotional tag: [{tag_content}]. Using pre-prompt: '{prompt_text.strip()}'")

        text_to_send = prompt_text + cleaned_text if has_emotion_prompt else text

        payload = {
            "text": text_to_send,
            "model_id": "eleven_v3",
            "voice_settings": final_settings
        }
        
        print(f"[DEBUG] [ElevenLabs TTS] Request Payload: Model={payload.get('model_id')}, Settings={payload.get('voice_settings')}")
        print(f"[DEBUG] [ElevenLabs TTS] Text to Send: '{payload.get('text')}'")

        output_path = os.path.join(self.output_dir, filename)
        alignment_data = []
        audio_duration = 0.0

        async with httpx.AsyncClient(timeout=180.0, trust_env=False) as client:
            response = None
            max_retries = 3
            retry_delay = 2.0

            for attempt in range(max_retries):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    
                    if response.status_code == 200:
                        break
                    
                    is_rate_limit = response.status_code == 429 or "concurrent" in response.text or "rate_limit" in response.text
                    if is_rate_limit and attempt < max_retries - 1:
                        sleep_time = retry_delay * (attempt + 1)
                        print(f"[WARN] [ElevenLabs TTS] Concurrency/Rate limit hit (Status {response.status_code}). Retrying in {sleep_time:.1f}s (Attempt {attempt+1}/{max_retries})...")
                        await asyncio.sleep(sleep_time)
                        continue
                    
                    if "voice_not_found" in response.text and voice_id != "4JJwo477JUAx3HV0T7n7":
                        print(f"⚠️ ElevenLabs voice '{voice_id}' not found. Falling back to default.")
                        return await self.generate_elevenlabs(text, "4JJwo477JUAx3HV0T7n7", filename, return_alignment, voice_settings)
                    else:
                        raise Exception(f"ElevenLabs API 오류: {response.text}")
                except Exception as e:
                    if "voice_not_found" in str(e):
                        raise e
                    if attempt < max_retries - 1:
                        sleep_time = retry_delay * (attempt + 1)
                        print(f"[WARN] [ElevenLabs TTS] Request exception: {e}. Retrying in {sleep_time:.1f}s...")
                        await asyncio.sleep(sleep_time)
                        continue
                    else:
                        raise e

            if response.status_code == 200:
                import json
                import base64
                import subprocess
                
                data = response.json()
                
                # 타이밍 정보 추출
                alignment = data.get("alignment", {})
                characters = alignment.get("characters", [])
                char_start_times = alignment.get("character_start_times_seconds", [])
                char_end_times = alignment.get("character_end_times_seconds", [])
                
                # [NEW] Pre-prompt Cropping Index calculation
                t_start = 0.0
                if has_emotion_prompt and characters and char_start_times:
                    split_idx = len(prompt_text)
                    found_idx = -1
                    
                    # Find the first character of cleaned_text in characters list starting from split_idx - 5
                    first_real_char = cleaned_text.strip()[0] if cleaned_text.strip() else ""
                    if first_real_char:
                        start_search = max(0, split_idx - 5)
                        for i in range(start_search, len(characters)):
                            if characters[i] == first_real_char:
                                found_idx = i
                                break
                                    
                    if found_idx == -1:
                        found_idx = split_idx
                        
                    # Get start timestamp
                    if 0 <= found_idx < len(char_start_times):
                        proposed_t_start = char_start_times[found_idx]
                        total_duration = char_end_times[-1] if char_end_times else 0.0
                        min_required = max(0.5, len(cleaned_text.strip()) * 0.1)
                        if proposed_t_start >= total_duration - min_required:
                            print(f"[TRIM] [ElevenLabs TTS] Crop safety triggered: proposed_t_start ({proposed_t_start:.3f}s) is too close to total duration ({total_duration:.3f}s), min required remaining is {min_required:.2f}s. Disabling cropping.")
                            t_start = 0.0
                        else:
                            t_start = proposed_t_start
                            print(f"[TRIM] [ElevenLabs TTS] Pre-prompt ended at character index {found_idx}, time {t_start:.3f}s. Trimming audio...")
                            
                            # Trim characters and timestamps only if cropping is active
                            characters = characters[found_idx:]
                            char_start_times = [t - t_start for t in char_start_times[found_idx:]]
                            char_end_times = [t - t_start for t in char_end_times[found_idx:]]

                # 오디오 데이터 (base64) 및 파일 저장 (필요한 경우 크롭 처리)
                audio_base64 = data.get("audio_base64", "")
                if audio_base64:
                    audio_bytes = base64.b64decode(audio_base64)
                    
                    if t_start > 0.05:
                        temp_path = output_path.replace(".mp3", "_temp_crop.mp3")
                        with open(temp_path, "wb") as f:
                            f.write(audio_bytes)
                            
                        # ffmpeg를 사용하여 pre-prompt 부분 잘라내기
                        try:
                            ffmpeg_exe = "ffmpeg"
                            try:
                                import imageio_ffmpeg
                                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                            except Exception:
                                pass
                                
                            cmd = [
                                ffmpeg_exe, "-y",
                                "-ss", f"{t_start:.3f}",
                                "-i", temp_path,
                                "-c:a", "libmp3lame",
                                "-q:a", "2",
                                output_path
                            ]
                            
                            startupinfo = None
                            if os.name == 'nt':
                                startupinfo = subprocess.STARTUPINFO()
                                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                                
                            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, startupinfo=startupinfo)
                            print(f"[TRIM] [ElevenLabs TTS] Cropped audio saved to {output_path}")
                        except Exception as crop_err:
                            print(f"[WARN] [ElevenLabs TTS] Cropping failed: {crop_err}. Saving full audio as fallback.")
                            with open(output_path, "wb") as f:
                                f.write(audio_bytes)
                        finally:
                            if os.path.exists(temp_path):
                                try: os.remove(temp_path)
                                except Exception: pass
                    else:
                        with open(output_path, "wb") as f:
                            f.write(audio_bytes)
                
                # 문자 타이밍을 단어 타이밍으로 변환
                if characters and char_start_times:
                    alignment_data = self._chars_to_words_alignment(
                        characters, char_start_times, char_end_times
                    )
                    
                    if alignment_data:
                        audio_duration = alignment_data[-1]["end"]
                
                # [NEW] Speed Adjustment Post-Processing
                if speed_factor != 1.0 and os.path.exists(output_path):
                    try:
                        print(f"[SPEED] Adjusting audio speed by {speed_factor}x...")
                        
                        ffmpeg_exe = "ffmpeg"
                        try:
                            import imageio_ffmpeg
                            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                        except Exception:
                            pass
                            
                        temp_speed_path = output_path.replace(".mp3", "_speed.mp3")
                        
                        cmd = [
                            ffmpeg_exe, "-y", "-i", output_path,
                            "-filter:a", f"atempo={speed_factor}",
                            "-vn", temp_speed_path
                        ]
                        
                        startupinfo = None
                        if os.name == 'nt':
                            startupinfo = subprocess.STARTUPINFO()
                            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        
                        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, startupinfo=startupinfo)
                        
                        if os.path.exists(temp_speed_path):
                            try:
                                os.remove(output_path)
                                os.rename(temp_speed_path, output_path)
                            except OSError:
                                import shutil
                                shutil.move(temp_speed_path, output_path)
                            
                            audio_duration = audio_duration / speed_factor
                            
                            if alignment_data:
                                for word in alignment_data:
                                    word["start"] = word["start"] / speed_factor
                                    word["end"] = word["end"] / speed_factor
                                
                            print(f"[SUCCESS] Speed adjustment complete. New duration: {audio_duration:.2f}s")
                    except Exception as e:
                        print(f"[WARN] Failed to adjust audio speed: {e}")

                # [NEW] Whisper-based Forced Alignment Override
                if os.path.exists(output_path):
                    whisper_alignment = self._align_with_whisper(output_path, text)
                    if whisper_alignment:
                        # 덮어쓰기 성공
                        alignment_data = whisper_alignment
                        audio_duration = alignment_data[-1]["end"] if alignment_data else audio_duration
                    else:
                        print("[ALIGN] Whisper alignment skipped or failed. Using native mathematical alignment.")

                # 타이밍 정보 저장
                alignment_path = output_path.replace(".mp3", "_alignment.json")
                with open(alignment_path, "w", encoding="utf-8") as f:
                    json.dump(alignment_data, f, ensure_ascii=False, indent=2)
                
                print(f"[SUCCESS] ElevenLabs TTS 생성 완료: {output_path} ({len(alignment_data)} words, {audio_duration:.1f}s)")
                
                return {
                    "audio_path": output_path,
                    "alignment": alignment_data,
                    "duration": audio_duration
                }
            elif "voice_not_found" in response.text and voice_id != "4JJwo477JUAx3HV0T7n7":
                print(f"⚠️ ElevenLabs voice '{voice_id}' not found. Falling back to default.")
                return await self.generate_elevenlabs(text, "4JJwo477JUAx3HV0T7n7", filename, return_alignment)
            else:
                raise Exception(f"ElevenLabs API 오류: {response.text}")




    async def get_elevenlabs_voices(self) -> list:
        """ElevenLabs 사용 가능한 음성 목록 조회"""
        load_dotenv(override=True)
        api_key = os.getenv("ELEVENLABS_API_KEY")
        if not api_key:
            return []

        url = "https://api.elevenlabs.io/v1/voices"
        headers = {"xi-api-key": api_key}
        
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("voices", [])
                else:
                    print(f"⚠️ ElevenLabs Voices Error: {response.status_code}")
                    return []
            except Exception as e:
                print(f"⚠️ Failed to fetch ElevenLabs voices: {e}")
                return []

    async def generate_sound_effect(self, text: str, duration_seconds: float = None) -> Optional[bytes]:
        """ElevenLabs Sound Effects 생성"""
        load_dotenv(override=True)
        api_key = os.getenv("ELEVENLABS_API_KEY")
        
        if not api_key:
            print("❌ ElevenLabs API Key Missing for SFX")
            return None

        url = "https://api.elevenlabs.io/v1/sound-generation"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }

        # [NOTE] ElevenLabs SFX API limits prompt length and has uncertain duration control
        # Currently, duration_seconds is 'prompt influence' or similar in some versions, 
        # but the standard endpoint is text -> audio.
        
        payload = {
            "text": text[:200], # Limit prompt length
            "duration_seconds": duration_seconds or 3.0, # Approximate if supported, otherwise ignored
            "prompt_influence": 0.3 # Default balanced
        }
        
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            try:
                # Use verify=False if certificate issues arise, but standard shouldn't need it
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    return response.content
                else:
                    print(f"❌ ElevenLabs SFX Error: {response.status_code} - {response.text}")
                    return None
            except Exception as e:
                print(f"❌ ElevenLabs SFX Exception: {e}")
                return None
    
    def _align_with_whisper(self, audio_path: str, original_text: str) -> list:
        """
        Whisper-timestamped 기반 강제 정렬 (Forced Alignment)
        생성된 TTS 오디오를 AI가 듣고 실제 파형 기준의 단어 타임스탬프를 반환.
        """
        try:
            import whisper_timestamped as whisper
            import torch
        except ImportError:
            print("[ALIGN] whisper-timestamped or torch not installed. Fallback to native alignment.")
            return []

        print("[ALIGN] Initializing Whisper model for Forced Alignment...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            # 렌더링용으로는 base 모델도 매우 정확하고 빠름
            model = whisper.load_model("base", device=device)
            audio = whisper.load_audio(audio_path)
            
            print(f"[{device.upper()}] Transcribing & Aligning audio for precise sync...")
            result = whisper.transcribe(model, audio, language="ko")
            
            alignment_data = []
            for segment in result.get("segments", []):
                for word_info in segment.get("words", []):
                    alignment_data.append({
                        "word": word_info["text"],
                        "start": word_info["start"],
                        "end": word_info["end"]
                    })
                    
            if alignment_data:
                print(f"[SUCCESS] Whisper Alignment complete. {len(alignment_data)} words aligned.")
            return alignment_data
        except Exception as e:
            print(f"[ERROR] Whisper Alignment failed: {e}")
            return []
    
    def _chars_to_words_alignment(self, characters: list, start_times: list, end_times: list) -> list:
        """문자 단위 타이밍을 단어 단위로 변환"""
        words = []
        current_word = ""
        word_start = None
        word_end = None
        
        for i, char in enumerate(characters):
            if i >= len(start_times):
                break
                
            if char.strip() == "" or char in " \n\t":
                # 공백 - 단어 종료
                if current_word:
                    words.append({
                        "word": current_word.strip(),
                        "start": word_start,
                        "end": word_end
                    })
                    current_word = ""
                    word_start = None
            else:
                # 문자 추가
                if word_start is None:
                    word_start = start_times[i]
                current_word += char
                word_end = end_times[i] if i < len(end_times) else start_times[i] + 0.1
        
        # 마지막 단어
        if current_word:
            words.append({
                "word": current_word.strip(),
                "start": word_start,
                "end": word_end
            })
        
        return words

    async def generate_gtts(
        self,
        text: str,
        lang: str = "ko",
        filename: str = "tts_output.mp3"
    ) -> Optional[str]:
        """gTTS (무료) 생성"""
        if not gTTS:
            raise ImportError("gTTS 라이브러리가 설치되지 않았습니다")

        try:
            tts = gTTS(text=text, lang=lang)
            output_path = os.path.join(self.output_dir, filename)
            tts.save(output_path)
            return output_path
        except Exception as e:
            raise Exception(f"gTTS 생성 실패: {str(e)}")

    async def generate_google_cloud(
        self,
        text: str,
        voice_name: str = "ko-KR-Neural2-A",
        language_code: str = "ko-KR",
        filename: str = "tts_output.mp3",
        speaking_rate: float = 1.0
    ) -> Optional[str]:
        """Google Cloud TTS 생성"""
        if not self.google_client:
            raise ValueError("Google Cloud TTS 클라이언트가 초기화되지 않았습니다. GOOGLE_APPLICATION_CREDENTIALS 설정을 확인하세요.")
        
        # [NEW] 문장 단위 분할 처리 (제한 5,000자, 안전빵 4,500자)
        max_chars = 4500
        if len(text) > max_chars:
            chunks = self._split_text(text, max_chars)
            print(f"DEBUG: Text too long ({len(text)} chars). Splitting into {len(chunks)} chunks for Google Cloud TTS.")
            
            chunk_files = []
            for i, chunk in enumerate(chunks):
                chunk_filename = f"temp_{i}_{filename}"
                chunk_path = await self.generate_google_cloud(chunk, voice_name, language_code, chunk_filename, speaking_rate)
                if chunk_path:
                    chunk_files.append(chunk_path)
            
            if not chunk_files:
                return None
            
            output_path = os.path.join(self.output_dir, filename)
            self._merge_audio_files(chunk_files, output_path)
            return output_path

        try:
            # [FIX] 텍스트 정제
            clean_text = self.clean_text(text)
            input_text = texttospeech.SynthesisInput(text=clean_text)
            
            # 음성 설정
            voice = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name
            )
            
            # 오디오 설정 (속도 조절 추가)
            # speaking_rate: 0.25 ~ 4.0
            rate = max(0.25, min(4.0, speaking_rate))
            
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=rate
            )
            
            response = self.google_client.synthesize_speech(
                input=input_text, voice=voice, audio_config=audio_config
            )
            
            output_path = os.path.join(self.output_dir, filename)
            with open(output_path, "wb") as f:
                f.write(response.audio_content)
                
            return output_path
            
        except Exception as e:

            raise Exception(f"Google Cloud TTS 생성 실패: {str(e)}")

    async def generate_openai(
        self,
        text: str,
        voice: str = "alloy",
        model: str = "tts-1",
        filename: str = "tts_output.mp3",
        speed: float = 1.0
    ) -> Optional[str]:
        """OpenAI TTS 생성"""
        if not self.openai_client:
            raise ValueError("OpenAI Client가 초기화되지 않았습니다. OPENAI_API_KEY 설정을 확인하세요.")

        # [NEW] 문장 단위 분할 처리 (제한 4,096자, 안전빵 4,000자)
        max_chars = 4000
        if len(text) > max_chars:
            chunks = self._split_text(text, max_chars)
            print(f"DEBUG: Text too long ({len(text)} chars). Splitting into {len(chunks)} chunks for OpenAI TTS.")
            
            chunk_files = []
            for i, chunk in enumerate(chunks):
                chunk_filename = f"temp_{i}_{filename}"
                chunk_path = await self.generate_openai(chunk, voice, model, chunk_filename, speed)
                if chunk_path:
                    chunk_files.append(chunk_path)
            
            if not chunk_files:
                return None
            
            output_path = os.path.join(self.output_dir, filename)
            self._merge_audio_files(chunk_files, output_path)
            return output_path

        try:
            # 속도 범위 제한 (0.25 - 4.0)
            safe_speed = max(0.25, min(4.0, speed))

            # [FIX] 텍스트 정제
            clean_text = self.clean_text(text)

            response = self.openai_client.audio.speech.create(
                model=model,
                voice=voice,
                input=clean_text,
                speed=safe_speed
            )
            
            output_path = os.path.join(self.output_dir, filename)
            response.stream_to_file(output_path)
            
            return output_path
            
        except Exception as e:
            raise Exception(f"OpenAI TTS 생성 실패: {str(e)}")


    def clean_text(self, text: str) -> str:
        """TTS를 위한 텍스트 정제 (괄호, 마크다운 제거)
        단, ElevenLabs용 감정 태그 [annoyed], [excited] 등은 유지함.
        """
        import re
        # 1. 마크다운 헤더/볼드 제거 (**, ## 등)
        text = re.sub(r'[\*#\-]+', '', text)
        
        # 2. 감정 태그/일시정지 태그 화이트리스트 (ElevenLabs용)
        # [annoyed], [excited], [sad], [angry], [shouting], [whispering], [long pause], [pause] 등
        emotion_tags = ["annoyed", "excited", "sad", "angry", "shouting", "whispering", "long pause", "pause", "appalled", "happy", "quietly", "thoughtful", "whispers", "shouts", "sigh"]
        
        # 괄호 내용 중 화이트리스트에 없는 것만 제거
        def remove_brackets_except_emotions(match):
            content = match.group(1).lower().strip()
            if any(tag in content for tag in emotion_tags):
                return match.group(0) # 유지
            return "" # 제거

        # [], () 중 ()는 한글 감정 지시어(예: (신나게))를 위해 보존하고 나머지만 처리
        text = re.sub(r'\[([^\]]*)\]', remove_brackets_except_emotions, text)
        # text = re.sub(r'\(([^)]*)\)', remove_brackets_except_emotions, text)  # 괄호 태그 전체 유지
        text = re.sub(r'<([^>]*)>', remove_brackets_except_emotions, text)
        
        # 전각 괄호 (일본어/한국어) - 이것도 지시어일 수 있으므로 유지
        # text = re.sub(r'（[^）]*）', '', text)
        # text = re.sub(r'［[^］]*］', '', text)
        
        # 3. 여러 공백 및 불필요한 기호 정리
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    async def generate_edge_tts(
        self,
        text: str,
        voice: str = "ko-KR-SunHiNeural",
        rate: str = "+0%", # "+10%", "-10%"
        filename: str = "tts_output.mp3"
    ) -> Optional[str]:
        """Edge TTS 생성 (무료, 고품질, 속도 조절 가능)"""
        try:
            import edge_tts
        except ImportError:
            print("Edge TTS 라이브러리가 없습니다.")
            return None

        output_path = os.path.join(self.output_dir, filename)
        
        # [NEW] 문장 단위 분할 처리 (Edge TTS는 약 30,000자 제한설이 있음, 안전하게 20,000자)
        max_chars = 20000
        if len(text) > max_chars:
            chunks = self._split_text(text, max_chars)
            print(f"DEBUG: Text too long ({len(text)} chars). Splitting into {len(chunks)} chunks for Edge TTS.")
            
            chunk_files = []
            for i, chunk in enumerate(chunks):
                # [FIX] filename이 절대 경로일 경우를 대비해 basename만 사용
                # 이렇게 해야 recursive 호출 시 output_dir와 중복 결합되지 않음.
                base_name = os.path.basename(filename)
                chunk_filename = f"temp_{i}_{base_name}"
                chunk_path = await self.generate_edge_tts(chunk, voice, rate, chunk_filename)
                if chunk_path:
                    chunk_files.append(chunk_path)
            
            if not chunk_files:
                return None
            
            output_path = os.path.join(self.output_dir, filename)
            self._merge_audio_files(chunk_files, output_path)
            # VTT는 합치기 복잡하므로 일단 무시 (MP3라도 건짐)
            return output_path

        # 텍스트 정제
        clean_text = self.clean_text(text)
        if not clean_text:
            return None

        communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
        
        # VTT 생성을 위한 자막 데이터 수집
        sub_events = []
        
        
        unique_types = set()
        with open(output_path, "wb") as file:
            async for chunk in communicate.stream():
                unique_types.add(chunk["type"])
                if chunk["type"] == "audio":
                    file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary" or chunk["type"] == "SentenceBoundary":
                    sub_events.append(chunk)

        # print(f"[DEBUG] Chunk types received: {unique_types}")
        # print(f"[DEBUG] Collected {len(sub_events)} events.")
        
        # SentenceBoundary가 섞여있으면 SentenceBoundary만 사용하는 것이 깔끔함 (중복 방지)
        sentence_events = [e for e in sub_events if e["type"] == "SentenceBoundary"]
        if sentence_events:
            sub_events = sentence_events
        
        # VTT 파일 저장 (같은 이름.vtt)
        vtt_path = output_path.replace(".mp3", ".vtt")
        self._save_vtt(sub_events, vtt_path)
            
        return output_path

    def _save_vtt(self, events, path):
        """WordBoundary 이벤트를 VTT 포맷으로 저장"""
        def format_time(offset_100ns):
            seconds = offset_100ns / 10_000_000
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            sec = seconds % 60
            return f"{hours:02d}:{minutes:02d}:{sec:06.3f}"

        with open(path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            
            # 문장 단위로 묶기 (간단히 단어 단위로 출력하고 프론트에서 합치거나, 여기서 합치거나)
            # Edge TTS WordBoundary는 단어 단위임. 너무 많아질 수 있음.
            # 일단 단어 단위로 생성하되, 겹치는 시간은 병합하는게 좋지만 시간이 없으므로
            # 단어 단위로 Just 생성 -> 자막이 너무 빨라질 수 있음. 
            # 하지만 편집을 위한 초안이므로 OK.
            
            # 개선: 인접한 단어들을 문장(50자 내외 또는 마침표)으로 묶는 로직
            current_sentence = []
            sentence_start = 0
            current_length = 0
            
            for i, event in enumerate(events):
                text = event["text"]
                offset = event["offset"]
                duration = event["duration"]
                
                if not current_sentence:
                    sentence_start = offset
                
                current_sentence.append(text)
                current_length += len(text)
                
                # 문장 종료 조건 (길이 or 마침표 or 마지막)
                is_end_of_sentence = text.endswith(('.', '?', '!')) or current_length > 30 or i == len(events) - 1
                
                if is_end_of_sentence:
                    start_time = format_time(sentence_start)
                    # 종료 시간은 현재 단어의 끝 (offset + duration)
                    end_time_val = offset + duration
                    
                    # 다음 단어의 시작 직전까지 늘려주는 보정 (부드러운 연결 위해)
                    if i < len(events) - 1:
                        next_offset = events[i+1]["offset"]
                        if next_offset > end_time_val:
                            # 공백(쉼)이 있으면 쉼. 너무 길면 유지.
                            if next_offset - end_time_val < 5_000_000: # 0.5초 이내면 이음
                                end_time_val = next_offset
                    
                    end_time = format_time(end_time_val)
                    full_text = " ".join(current_sentence)
                    
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{full_text}\n\n")
                    
                    current_sentence = []
                    current_length = 0


    async def generate_gemini(
        self,
        text: str,
        voice_name: str = "Puck",
        language_code: str = "ko-KR",
        style_prompt: Optional[str] = None,
        filename: str = "tts_output.mp3",
        speed: float = 1.0
    ) -> Optional[str]:
        """Gemini TTS 생성 (Experimental) -> Edge TTS fallback"""
        # 현재 Gemini REST API의 Audio Output 모달리티가 불안정하므로
        # Edge TTS로 우회하여 고품질/속도제어 지원
        print(f"DEBUG: Gemini TTS falling back to Edge TTS due to API limitations.")
        
        # [Speed Logic]
        # Edge TTS rate format: "+30%", "-10%"
        # speed 1.0 -> +0%
        # speed 1.5 -> +50%
        # Limit speed to typical range 0.5 ~ 2.0
        safe_speed = max(0.5, min(2.0, speed))
        rate_val = int((safe_speed - 1.0) * 100)
        rate_str = f"{rate_val:+d}%"

        # Language Code based Voice Selection
        lang = language_code.lower() if language_code else "ko"
        
        # [ROBUSTNESS]: 텍스트 내용 기반 언어 자동 감지
        import re
        
        # 1. 일본어 자동 감지 (히라가나/가타카나)
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FBF]', text):
            if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):
                lang = "ja"
                print(f"DEBUG: Detected Japanese text. Forcing language to 'ja'.")
        
        # 2. 영어 자동 감지 (한글/일본어가 없고 영어가 있는 경우)
        # ko 설정인데 한글/일본어 문자가 없고 알파벳이 있다면 영어로 판단
        elif lang.startswith("ko") and re.search(r'[a-zA-Z]', text):
            if not re.search(r'[가-힣\u3040-\u30ff]', text):
                lang = "en"
                print(f"DEBUG: Detected English-only text. Forcing language to 'en'.")
        
        if lang.startswith("ja"): # Japanese
            # Gemini Voice Name Mapping for Japanese
            # Puck/Charon/Fenrir (Male) -> KeitaNeural
            # Kore/Aoede (Female) -> NanamiNeural
            if voice_name in ["Puck", "Charon", "Fenrir"]:
                target_voice = "ja-JP-KeitaNeural"
            else:
                target_voice = "ja-JP-NanamiNeural"
                
        elif lang.startswith("en"): # English
            if voice_name in ["Puck", "Charon", "Fenrir"]:
                target_voice = "en-US-GuyNeural"
            else:
                target_voice = "en-US-JennyNeural"
                
        else: # Korean (Default)
            # 확장된 한국어 음성 맵 (Edge TTS 지원 목록 활용)
            voice_map = {
                # 남성향 (Male)
                "Puck": "ko-KR-InJoonNeural",
                "Charon": "ko-KR-BongJinNeural",
                "Fenrir": "ko-KR-GookMinNeural",
                "Atlas": "ko-KR-InJoonNeural", 
                
                # 여성향 (Female)
                "Kore": "ko-KR-SunHiNeural",
                "Aoede": "ko-KR-JiMinNeural",
                "Hestia": "ko-KR-SeoHyeonNeural",
                "Iris": "ko-KR-SoonBokNeural",
                "Calliope": "ko-KR-YuJinNeural"
            }
            
            # [FIX] If voice_name appears to be a full ID (e.g. ko-KR-...), use it directly
            if "-" in voice_name and len(voice_name) > 10:
                target_voice = voice_name
            else:
                target_voice = voice_map.get(voice_name, "ko-KR-SunHiNeural")
        
        return await self.generate_edge_tts(text, target_voice, rate_str, filename)

    def _split_text(self, text: str, max_chars: int) -> list:
        """텍스트를 문장 단위로 분할"""
        if len(text) <= max_chars:
            return [text]
            
        import re
        # 문장 종결자 기준으로 분할 (마침표, 물음표, 느낌표, 개행)
        # 공백을 포함하도록 긍정형 전방 탐색 사용
        sentences = re.split(r'(?<=[.?!])\s+|\n', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence: continue
            
            if len(current_chunk) + len(sentence) + 1 <= max_chars:
                current_chunk += (sentence + " ")
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # 문장 하나가 max_chars를 초과하는 경우 강제 절단
                if len(sentence) > max_chars:
                    while len(sentence) > max_chars:
                        chunks.append(sentence[:max_chars])
                        sentence = sentence[max_chars:]
                    current_chunk = sentence + " "
                else:
                    current_chunk = sentence + " "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    def _merge_audio_files(self, audio_files: list, output_path: str):
        """여러 오디오 파일을 하나로 합침"""
        if not AudioFileClip or not concatenate_audioclips:
            raise ImportError("MoviePy가 설치되지 않았습니다. 오디오 합치기가 불가능합니다.")
            
        clips = []
        try:
            for f in audio_files:
                clips.append(AudioFileClip(f))
            
            final_clip = concatenate_audioclips(clips)
            # FFmpeg 로그 억제 (verbose=False, logger=None)
            final_clip.write_audiofile(output_path, verbose=False, logger=None)
            final_clip.close()
        finally:
            for clip in clips:
                try: clip.close()
                except Exception: pass
            
            # 임시 파일 삭제
            for f in audio_files:
                if os.path.exists(f) and f != output_path:
                    try: os.remove(f)
                    except Exception: pass


# 싱글톤 인스턴스
tts_service = TTSService()
