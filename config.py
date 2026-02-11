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
    REPLICATE_API_TOKEN: str = os.getenv("REPLICATE_API_TOKEN", "") # Replicate AI Video
    AKOOL_TOKEN: str = os.getenv("AKOOL_TOKEN", "") # Akool Creative AI
    TOPVIEW_API_KEY: str = os.getenv("TOPVIEW_API_KEY", "") # TopView AI

    # 서버 설정
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 8000))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # API URLs
    YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    PEXELS_BASE_URL = "https://api.pexels.com/videos"

    # 경로 설정
    import sys
    
    # [FIX] PyInstaller Support: Split Resource vs Data paths
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE
        # Resources (templates/static) are internally packed in _MEIPASS
        RESOURCE_DIR = sys._MEIPASS
        # Data (Output, DB, Env) should be in the folder where EXE is located
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        # Running as script
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        RESOURCE_DIR = BASE_DIR

    TEMPLATES_DIR = os.path.join(RESOURCE_DIR, "templates")
    STATIC_DIR = os.path.join(RESOURCE_DIR, "static")
    
    # Output/Logs/DB must live in BASE_DIR (Writeable)
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    
    # 하드코딩된 상수 관리
    # [FIX] Better font discovery for Windows
    DEFAULT_FONT_PATH = "C:/Windows/Fonts/malgun.ttf" if os.path.exists("C:/Windows/Fonts/malgun.ttf") else "malgun.ttf"
    DEBUG_LOG_PATH = os.path.join(LOG_DIR, "debug.log")

    
    # [NEW] FFmpeg Path for services
    try:
        import imageio_ffmpeg
        FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        FFMPEG_PATH = "ffmpeg"


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
        valid_keys = ['YOUTUBE_API_KEY', 'GEMINI_API_KEY', 'ELEVENLABS_API_KEY', 'TYPECAST_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS', 'OPENAI_API_KEY', 'PEXELS_API_KEY', 'REPLICATE_API_TOKEN', 'TOPVIEW_API_KEY', 'AKOOL_TOKEN']

        if key_name not in valid_keys:
            return False

        # 런타임 업데이트
        setattr(cls, key_name, value)
        os.environ[key_name] = value  # [ADD] 업기 위해 환경변수도 즉시 업데이트

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
            },
            "replicate": {
                "set": bool(cls.REPLICATE_API_TOKEN),
                "masked": mask_key(cls.REPLICATE_API_TOKEN)
            },
            "akool": {
                "set": bool(cls.AKOOL_TOKEN),
                "masked": mask_key(cls.AKOOL_TOKEN)
            },
            "topview": {
                "set": bool(cls.TOPVIEW_API_KEY),
                "masked": mask_key(cls.TOPVIEW_API_KEY)
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
