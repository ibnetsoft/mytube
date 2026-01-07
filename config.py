"""
피카디리스튜디오 설정 관리
"""
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    # Google API
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    # TTS Keys
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    TYPECAST_API_KEY: str = os.getenv("TYPECAST_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "") # OpenAI TTS
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "") # Pexels Stock Video

    # 서버 설정
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 8000))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # API URLs
    YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    PEXELS_BASE_URL = "https://api.pexels.com/videos"

    # 경로 설정
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
    STATIC_DIR = os.path.join(BASE_DIR, "static")
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    
    # 하드코딩된 상수 관리
    DEFAULT_FONT_PATH = "malgun.ttf"  # 시스템에 설치된 맑은 고딕 또는 폰트 파일 경로
    DEBUG_LOG_PATH = os.path.join(LOG_DIR, "debug.log")

    @classmethod
    def setup_directories(cls):
        """필요한 디렉토리 생성"""
        for d in [cls.OUTPUT_DIR, cls.LOG_DIR]:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)

    @classmethod
    def validate(cls):
        """필수 API 키 확인"""
        missing = []
        if not cls.YOUTUBE_API_KEY:
            missing.append("YOUTUBE_API_KEY")
        if not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")

        if missing:
            print(f"⚠️  경고: 다음 API 키가 설정되지 않았습니다: {', '.join(missing)}")
            print("   .env 파일을 확인해주세요.")
            return False
        return True

    @classmethod
    def update_api_key(cls, key_name: str, value: str):
        """API 키 런타임 업데이트 및 .env 파일 저장"""
        valid_keys = ['YOUTUBE_API_KEY', 'GEMINI_API_KEY', 'ELEVENLABS_API_KEY', 'TYPECAST_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS', 'OPENAI_API_KEY', 'PEXELS_API_KEY']

        if key_name not in valid_keys:
            return False

        # 런타임 업데이트
        setattr(cls, key_name, value)

        # .env 파일 업데이트
        env_path = os.path.join(cls.BASE_DIR, '.env')

        # 기존 .env 파일 읽기
        env_lines = []
        key_exists = False

        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith(f'{key_name}='):
                        env_lines.append(f'{key_name}={value}\n')
                        key_exists = True
                    else:
                        env_lines.append(line)

        # 키가 없으면 추가
        if not key_exists:
            env_lines.append(f'{key_name}={value}\n')

        # .env 파일 저장
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)

        return True

    @classmethod
    def get_api_keys_status(cls):
        """API 키 상태 반환 (마스킹된 값)"""
        def mask_key(key: str) -> str:
            if not key:
                return ""
            if len(key) <= 8:
                return "*" * len(key)
            return key[:4] + "*" * (len(key) - 8) + key[-4:]

        return {
            "youtube": {
                "set": bool(cls.YOUTUBE_API_KEY),
                "masked": mask_key(cls.YOUTUBE_API_KEY)
            },
            "gemini": {
                "set": bool(cls.GEMINI_API_KEY),
                "masked": mask_key(cls.GEMINI_API_KEY)
            },
            "elevenlabs": {
                "set": bool(cls.ELEVENLABS_API_KEY),
                "masked": mask_key(cls.ELEVENLABS_API_KEY)
            },
            "typecast": {
                "set": bool(cls.TYPECAST_API_KEY),
                "masked": mask_key(cls.TYPECAST_API_KEY)
            },
            "google_cloud": {
                "set": bool(cls.GOOGLE_APPLICATION_CREDENTIALS),
                "masked": mask_key(cls.GOOGLE_APPLICATION_CREDENTIALS)
            },
            "openai": {
                "set": bool(cls.OPENAI_API_KEY),
                "masked": mask_key(cls.OPENAI_API_KEY)
            }
        }

    @classmethod
    def get_kst_time(cls):
        """한국 표준시(KST) 현재 시간 반환"""
        from datetime import datetime, timezone, timedelta
        kst = timezone(timedelta(hours=9))
        return datetime.now(kst)

config = Config()
config.setup_directories()
