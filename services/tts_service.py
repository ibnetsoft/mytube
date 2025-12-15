"""
TTS (Text-to-Speech) 서비스
- ElevenLabs (유료, 고품질)
- Google Cloud TTS (유료, 고품질)
- gTTS (무료, Google 번역 기반)
"""
import httpx
import os
from typing import Optional

from config import config

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


class TTSService:
    def __init__(self):
        self.elevenlabs_key = config.ELEVENLABS_API_KEY
        self.typecast_key = config.TYPECAST_API_KEY
        self.google_credentials = config.GOOGLE_APPLICATION_CREDENTIALS
        self.output_dir = config.OUTPUT_DIR
        
        # Google Cloud Client 초기화 (설정된 경우)
        if self.google_credentials and os.path.exists(self.google_credentials) and texttospeech:
            try:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.google_credentials
                self.google_client = texttospeech.TextToSpeechClient()
            except Exception as e:
                print(f"Google Cloud TTS 초기화 실패: {e}")
                self.google_client = None
        else:
            self.google_client = None

    async def generate_elevenlabs(
        self,
        text: str,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        filename: str = "tts_output.mp3"
    ) -> Optional[str]:
        """ElevenLabs TTS 생성"""
        if not self.elevenlabs_key:
            raise ValueError("ElevenLabs API 키가 설정되지 않았습니다")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": self.elevenlabs_key,
            "Content-Type": "application/json"
        }

        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                output_path = os.path.join(self.output_dir, filename)
                with open(output_path, "wb") as f:
                    f.write(response.content)
                return output_path
            else:
                raise Exception(f"ElevenLabs API 오류: {response.text}")

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
        filename: str = "tts_output.mp3"
    ) -> Optional[str]:
        """Google Cloud TTS 생성"""
        if not self.google_client:
            raise ValueError("Google Cloud TTS 클라이언트가 초기화되지 않았습니다. GOOGLE_APPLICATION_CREDENTIALS 설정을 확인하세요.")
        
        try:
            input_text = texttospeech.SynthesisInput(text=text)
            
            # 음성 설정
            voice = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name
            )
            
            # 오디오 설정
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
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

    async def get_elevenlabs_voices(self) -> list:
        """ElevenLabs 사용 가능한 음성 목록"""
        if not self.elevenlabs_key:
            return []

        url = "https://api.elevenlabs.io/v1/voices"

        headers = {
            "xi-api-key": self.elevenlabs_key
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                return [
                    {
                        "voice_id": v["voice_id"],
                        "name": v["name"],
                        "labels": v.get("labels", {})
                    }
                    for v in data.get("voices", [])
                ]
            return []


# 싱글톤 인스턴스
tts_service = TTSService()
