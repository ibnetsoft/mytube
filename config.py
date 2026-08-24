"""
피카딜리스튜디오 설정 관리
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def _load_packaged_env():
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / ".env")
        candidates.append(Path(sys.executable).resolve().parent / ".env")
        candidates.append(Path(sys.executable).resolve().parent / "_internal" / ".env")
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path(__file__).resolve().parent / ".env")
    for path in candidates:
        try:
            if path and path.exists():
                load_dotenv(path, override=False)
        except Exception:
                pass


def _load_project_env_override():
    """Make the repository .env authoritative for local worker runs."""
    project_env = Path(__file__).resolve().parent / ".env"
    if project_env.exists():
        load_dotenv(project_env, override=True)


def _load_youtube_key_pool_from_env_files():
    """Read all YouTube key entries, including legacy duplicate key lines."""
    values = [os.getenv("YOUTUBE_API_KEYS", "")]
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"]
    seen_paths = set()
    for path in candidates:
        path = path.resolve()
        if path in seen_paths or not path.exists():
            continue
        seen_paths.add(path)
        try:
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                name, separator, value = line.partition("=")
                if separator and name.strip() in {"YOUTUBE_API_KEY", "YOUTUBE_API_KEYS"}:
                    values.append(value.strip())
        except Exception:
            pass
    return ",".join(value for value in values if value)


# .env 파일 로드
load_dotenv()
_load_packaged_env()
_load_project_env_override()

class Config:
    # Supabase (Cloud Sync)
    NEXT_PUBLIC_SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Google API
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
    # Optional comma/semicolon/newline-separated failover keys.
    YOUTUBE_API_KEYS = _load_youtube_key_pool_from_env_files()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    GLM_API_KEY = os.getenv("GLM_API_KEY", os.getenv("ZAI_API_KEY", os.getenv("Z_AI_API_KEY", "")))
    GLM_BASE_URL = os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")

    # AI Model Settings
    SCRIPT_GENERATION_MODEL = os.getenv("SCRIPT_GENERATION_MODEL", "gemini-3.6-flash")  # 대본 생성 모델
    # Keep local/offline defaults on a broadly available text model. The
    # web-admin settings override these values in production.
    TOPIC_GENERATION_MODEL = os.getenv("TOPIC_GENERATION_MODEL", "gemini-3.6-flash")
    TITLE_GENERATION_MODEL = os.getenv("TITLE_GENERATION_MODEL", os.getenv("SCRIPT_GENERATION_MODEL", "gemini-3.6-flash"))
    SCRIPT_PLANNING_MODEL = os.getenv("SCRIPT_PLANNING_MODEL", "gemini-3.6-flash")
    IMAGE_PROMPT_MODEL = os.getenv("IMAGE_PROMPT_MODEL", "gemini-3.6-flash")
    TRANSLATION_MODEL = os.getenv("TRANSLATION_MODEL", "gemini-3.6-flash")
    IMAGE_GENERATION_MODEL = os.getenv("IMAGE_GENERATION_MODEL", "gemini-3.1-flash-image-preview")  # 이미지 생성 모델
    VIDEO_GENERATION_MODEL = os.getenv("VIDEO_GENERATION_MODEL", "veo-3.1-fast-generate-preview")  # 영상 생성 모델

    # TTS Keys
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    # Voicebox (로컬 TTS 서버 - docs.voicebox.sh, 인증 없음)
    VOICEBOX_BASE_URL: str = os.getenv("VOICEBOX_BASE_URL", "http://127.0.0.1:17493")
    VOICEBOX_ENGINE: str = os.getenv("VOICEBOX_ENGINE", "qwen")
    VOICEBOX_MODEL_SIZE: str = os.getenv("VOICEBOX_MODEL_SIZE", "1.7B")
    SUNO_API_KEY: str = os.getenv("SUNO_API_KEY", "")
    SUNO_API_BASE_URL: str = os.getenv("SUNO_API_BASE_URL", "")
    MUSIC_PROVIDER: str = os.getenv("MUSIC_PROVIDER", "elevenlabs")
    MUSIC_GEMINI_MODEL: str = os.getenv("MUSIC_GEMINI_MODEL", "lyria-3-pro-preview")
    MUSIC_GEMINI_BASE_URL: str = os.getenv("MUSIC_GEMINI_BASE_URL", "")
    MUSIC_GEMINI_PROJECT_ID: str = os.getenv("MUSIC_GEMINI_PROJECT_ID", "")
    MUSIC_GEMINI_LOCATION: str = os.getenv("MUSIC_GEMINI_LOCATION", "global")
    TYPECAST_API_KEY: str = os.getenv("TYPECAST_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "") # OpenAI TTS
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "") # Pexels Stock Video
    TOPVIEW_API_KEY: str = os.getenv("TOPVIEW_API_KEY", "") # TopView AI
    TOPVIEW_UID: str = os.getenv("TOPVIEW_UID", "") # TopView AI UID

    # 서버 설정
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 8000))
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Remote rendering. USE_EXTERNAL_RENDER now means Google Drive API +
    # Supabase remote_render_queue. DRIVE_RENDER_QUEUE_PATH is legacy-only.
    USE_EXTERNAL_RENDER = os.getenv("USE_EXTERNAL_RENDER", "false").lower() == "true"
    DRIVE_RENDER_QUEUE_PATH = os.getenv("DRIVE_RENDER_QUEUE_PATH", "G:/내 드라이브/Longform_Render_Queue")
    DRIVE_PATH_KO = os.getenv("DRIVE_PATH_KO", "G:/내 드라이브/Longform_Render_Queue")
    DRIVE_PATH_EN = os.getenv("DRIVE_PATH_EN", "G:/My Drive/Longform_Render_Queue")
    DRIVE_PATH_JA = os.getenv("DRIVE_PATH_JA", "G:/マ이드라이브/Longform_Render_Queue")
    DRIVE_ACTIVE_LANG = os.getenv("DRIVE_ACTIVE_LANG", "ko")
    REMOTE_RENDER_DRIVE_FOLDER_ID = os.getenv("REMOTE_RENDER_DRIVE_FOLDER_ID", "")
    REMOTE_RENDER_GOOGLE_TOKEN_PATH = os.getenv("REMOTE_RENDER_GOOGLE_TOKEN_PATH", "")

    # API URLs
    YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent"
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

    # 패키징된 릴리즈 버전 (tools/build_windows.ps1이 빌드 시 BASE_DIR에 기록)
    APP_VERSION = ""
    try:
        import json as _json
        # utf-8-sig: tools/build_windows.ps1 writes this with `Set-Content -Encoding UTF8`,
        # which in Windows PowerShell 5.1 always emits a UTF-8 BOM. Plain "utf-8" then
        # fails to parse (JSONDecodeError -> silently swallowed below -> APP_VERSION
        # stays "" and the sidebar version display never renders).
        with open(os.path.join(BASE_DIR, "version.json"), "r", encoding="utf-8-sig") as _vf:
            APP_VERSION = _json.load(_vf).get("version", "")
    except Exception:
        # Development runs do not have the packaged version.json. Keep the
        # sidebar version visible by falling back to the source version marker.
        try:
            from version import APP_VERSION as _source_app_version
            APP_VERSION = str(_source_app_version or "")
        except Exception:
            APP_VERSION = ""

    # Writable local app storage shared by dev and installed builds.
    # AppData is local Windows storage, not Supabase. Supabase sync is handled separately.
    _LOCALAPPDATA = os.getenv("LOCALAPPDATA")
    _USERPROFILE = os.getenv("USERPROFILE")
    if _LOCALAPPDATA:
        LOCAL_APP_DATA_DIR = os.path.join(_LOCALAPPDATA, "AIRStudio")
    elif _USERPROFILE:
        LOCAL_APP_DATA_DIR = os.path.join(_USERPROFILE, "AppData", "Local", "AIRStudio")
    else:
        LOCAL_APP_DATA_DIR = os.path.join(BASE_DIR, "air_data")

    DATA_DIR = os.path.join(LOCAL_APP_DATA_DIR, "data")
    DB_DIR = DATA_DIR
    DB_PATH = os.path.join(DB_DIR, "wingsai.db")
    BALANCE_CACHE_PATH = os.path.join(LOCAL_APP_DATA_DIR, ".token_balance")
    WALLET_KEY_PATH = os.path.join(LOCAL_APP_DATA_DIR, ".wallet_key")

    # Default output/log dirs before login. login_user() switches these to per-email folders.
    OUTPUT_DIR = os.path.join(LOCAL_APP_DATA_DIR, "output")
    LOG_DIR = os.path.join(LOCAL_APP_DATA_DIR, "logs")
    ASSETS_DIR = os.path.join(LOCAL_APP_DATA_DIR, "assets") # [NEW] Added for templates/presets
    UPLOADS_DIR = os.path.join(LOCAL_APP_DATA_DIR, "uploads")
    MEDIA_DIR = OUTPUT_DIR # Alias for now
    
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
        for d in [
            cls.LOCAL_APP_DATA_DIR,
            cls.DATA_DIR,
            cls.DB_DIR,
            cls.OUTPUT_DIR,
            cls.LOG_DIR,
            cls.ASSETS_DIR,
            cls.UPLOADS_DIR,
        ]:
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
    def load_remote_keys(cls, keys: dict):
        """Supabase에서 받은 API 키를 메모리에만 올림 (파일 저장 없음).
        로컬 앱 재시작 시 Supabase에서 다시 받아오므로 로컬 저장 불필요."""
        valid_keys = {
            'GEMINI_API_KEY', 'YOUTUBE_API_KEY', 'YOUTUBE_API_KEYS', 'CLAUDE_API_KEY',
            'DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'GLM_API_KEY', 'GLM_BASE_URL',
            'ELEVENLABS_API_KEY', 'SUNO_API_KEY', 'SUNO_API_BASE_URL', 'MUSIC_PROVIDER',
            'MUSIC_GEMINI_MODEL', 'MUSIC_GEMINI_BASE_URL', 'MUSIC_GEMINI_PROJECT_ID', 'MUSIC_GEMINI_LOCATION',
            'TOPVIEW_API_KEY', 'TOPVIEW_UID',
            'REMOTE_RENDER_DRIVE_FOLDER_ID', 'REMOTE_RENDER_GOOGLE_TOKEN_PATH',
            'LONGFORM_MIN_DURATION_MINUTES', 'LONGFORM_BASE_PAYOUT',
            'LONGFORM_EXTRA_MINUTE_PAYOUT', 'LONGFORM_DURATION_LOCK_ENABLED',
            'TOPIC_GENERATION_MODEL', 'TITLE_GENERATION_MODEL', 'SCRIPT_PLANNING_MODEL',
            'SCRIPT_GENERATION_MODEL', 'IMAGE_PROMPT_MODEL', 'TRANSLATION_MODEL',
            'IMAGE_GENERATION_MODEL', 'VIDEO_GENERATION_MODEL',
        }
        loaded = []
        for key_name, value in keys.items():
            if key_name in valid_keys and value:
                # A local .env key is an explicit machine-level override. Do
                # not replace it with a stale web-admin key during worker jobs.
                local_override_keys = {
                    'GEMINI_API_KEY', 'CLAUDE_API_KEY', 'DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL',
                    'GLM_API_KEY', 'GLM_BASE_URL',
                    'TOPIC_GENERATION_MODEL', 'TITLE_GENERATION_MODEL',
                    'SCRIPT_PLANNING_MODEL', 'SCRIPT_GENERATION_MODEL',
                    'IMAGE_PROMPT_MODEL', 'TRANSLATION_MODEL',
                }
                if key_name in local_override_keys and os.getenv(key_name, '').strip():
                    continue
                setattr(cls, key_name, value)
                os.environ[key_name] = value   # 동일 프로세스 내 서브서비스도 참조 가능
                loaded.append(key_name)
        if loaded:
            cls.normalize_generation_models()
            import logging
            logging.getLogger(__name__).info(f"🔑 [Config] Supabase 원격 키 로드 완료: {loaded}")
        return loaded

    @classmethod
    def normalize_generation_models(cls):
        """Normalize text-generation model ids before a worker starts a job."""
        replacements = {
            "gemini-2.5-pro": "gemini-3.6-flash",
            "gemini-2.5-flash": "gemini-3.6-flash",
            "gemini-2.0-flash": "gemini-3.6-flash",
            "gemini-3-flash-preview": "gemini-3.6-flash",
        }
        for key_name in (
            "TOPIC_GENERATION_MODEL",
            "TITLE_GENERATION_MODEL",
            "SCRIPT_PLANNING_MODEL",
            "SCRIPT_GENERATION_MODEL",
            "IMAGE_PROMPT_MODEL",
            "TRANSLATION_MODEL",
        ):
            current = str(getattr(cls, key_name, "") or "").strip()
            replacement = replacements.get(current.lower())
            if replacement:
                setattr(cls, key_name, replacement)
                os.environ[key_name] = replacement

    @classmethod
    def validate_generation_models(cls):
        """Return invalid model settings without making a worker process crash."""
        cls.normalize_generation_models()
        required = {
            "TOPIC_GENERATION_MODEL": cls.TOPIC_GENERATION_MODEL,
            "SCRIPT_PLANNING_MODEL": cls.SCRIPT_PLANNING_MODEL,
            "SCRIPT_GENERATION_MODEL": cls.SCRIPT_GENERATION_MODEL,
        }
        return [key_name for key_name, value in required.items() if not str(value or "").strip()]

    @classmethod
    def load_remote_keys_from_supabase(cls):
        """웹어드민 Supabase global_settings의 공용 API 키를 우선 로드합니다."""
        try:
            from services.web_admin_client import web_admin_client
            keys = web_admin_client.fetch_global_api_keys()
            loaded = cls.load_remote_keys(keys)
            if loaded:
                print(f"[Config] Loaded API keys from web admin: {loaded}")
            return loaded
        except Exception as e:
            print(f"[Config] Supabase API key load failed: {e}")
            return []

    _last_remote_refresh_ts = 0.0
    _REMOTE_REFRESH_INTERVAL_SEC = 60

    @classmethod
    def refresh_remote_keys_if_stale(cls):
        """load_remote_keys_from_supabase()는 지금까지 앱 시작 시 딱 한 번만
        호출됐다 - 즉 웹어드민에서 '대본 생성 모델'을 Claude Sonnet으로 바꿔도
        앱을 재시작하기 전까지는 반영되지 않고 계속 이전 모델(사실상 하드코딩된
        것처럼 보이는)로 생성이 진행됐다. 실제 대본 생성 직전에 이 메서드를
        호출해 매번 네트워크 조회를 하지 않으면서도(60초 쓰로틀) 설정 변경이
        재시작 없이 곧 반영되도록 한다."""
        import time
        now = time.time()
        if now - cls._last_remote_refresh_ts < cls._REMOTE_REFRESH_INTERVAL_SEC:
            return
        cls._last_remote_refresh_ts = now
        cls.load_remote_keys_from_supabase()

    @classmethod
    def update_api_key(cls, key_name: str, value: str):
        """API 키 런타임 업데이트 및 .env 파일 저장"""
        valid_keys = [
            'NEXT_PUBLIC_SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY',
            'YOUTUBE_API_KEY', 'YOUTUBE_API_KEYS', 'GEMINI_API_KEY', 'CLAUDE_API_KEY',
            'DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL', 'GLM_API_KEY', 'GLM_BASE_URL',
            'ELEVENLABS_API_KEY', 'TYPECAST_API_KEY',
            'VOICEBOX_BASE_URL', 'VOICEBOX_ENGINE', 'VOICEBOX_MODEL_SIZE',
            'SUNO_API_KEY', 'SUNO_API_BASE_URL', 'MUSIC_PROVIDER',
            'MUSIC_GEMINI_MODEL', 'MUSIC_GEMINI_BASE_URL', 'MUSIC_GEMINI_PROJECT_ID', 'MUSIC_GEMINI_LOCATION',
            'GOOGLE_APPLICATION_CREDENTIALS', 'OPENAI_API_KEY', 'PEXELS_API_KEY',
            'TOPVIEW_API_KEY', 'TOPVIEW_UID',
            'BLOG_CLIENT_ID', 'BLOG_CLIENT_SECRET', 'BLOG_ID',
            'WP_URL', 'WP_USERNAME', 'WP_PASSWORD',
            'USE_EXTERNAL_RENDER', 'DRIVE_RENDER_QUEUE_PATH',
            'DRIVE_PATH_KO', 'DRIVE_PATH_EN', 'DRIVE_PATH_JA', 'DRIVE_ACTIVE_LANG',
            'REMOTE_RENDER_DRIVE_FOLDER_ID', 'REMOTE_RENDER_GOOGLE_TOKEN_PATH',
            'LONGFORM_MIN_DURATION_MINUTES', 'LONGFORM_BASE_PAYOUT',
            'LONGFORM_EXTRA_MINUTE_PAYOUT', 'LONGFORM_DURATION_LOCK_ENABLED',
            'TOPIC_GENERATION_MODEL', 'TITLE_GENERATION_MODEL', 'SCRIPT_PLANNING_MODEL',
            'SCRIPT_GENERATION_MODEL', 'IMAGE_PROMPT_MODEL', 'TRANSLATION_MODEL',
            'IMAGE_GENERATION_MODEL', 'VIDEO_GENERATION_MODEL',
        ]

        if key_name not in valid_keys:
            return False

        # 런타임 업데이트
        if key_name == 'YOUTUBE_API_KEYS':
            import re
            value = ",".join(part.strip() for part in re.split(r"[,;\r\n]+", str(value or "")) if part.strip())

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

        # [CRITICAL] 명시적으로 클래스 변수 재설정 (get_api_keys_status에서 참조함)
        setattr(cls, key_name, value)
        
        return True

    @staticmethod
    def mask_key(key: str) -> str:
        """키 마스킹 유틸리티"""
        if not key:
            return ""
        if len(key) <= 8:
            return "*" * len(key)
        return f"{key[:4]}****{key[-4:]}"

    @classmethod
    def get_api_keys_status(cls):
        """API 키 상태 반환 (마스킹된 값 및 원본 값)"""
        youtube_keys = cls.youtube_api_keys()
        return {
            "youtube": {"set": bool(youtube_keys), "masked": cls.mask_key(cls.YOUTUBE_API_KEY), "value": cls.YOUTUBE_API_KEY, "fallback_count": len(youtube_keys[:5])},
            "gemini": {"set": bool(cls.GEMINI_API_KEY), "masked": cls.mask_key(cls.GEMINI_API_KEY), "value": cls.GEMINI_API_KEY},
            "deepseek": {"set": bool(cls.DEEPSEEK_API_KEY), "masked": cls.mask_key(cls.DEEPSEEK_API_KEY), "value": cls.DEEPSEEK_API_KEY},
            "deepseek_base_url": {"set": bool(cls.DEEPSEEK_BASE_URL), "masked": cls.DEEPSEEK_BASE_URL, "value": cls.DEEPSEEK_BASE_URL},
            "glm": {"set": bool(cls.GLM_API_KEY), "masked": cls.mask_key(cls.GLM_API_KEY), "value": cls.GLM_API_KEY},
            "glm_base_url": {"set": bool(cls.GLM_BASE_URL), "masked": cls.GLM_BASE_URL, "value": cls.GLM_BASE_URL},
            "elevenlabs": {"set": bool(cls.ELEVENLABS_API_KEY), "masked": cls.mask_key(cls.ELEVENLABS_API_KEY), "value": cls.ELEVENLABS_API_KEY},
            "suno": {"set": bool(cls.SUNO_API_KEY), "masked": cls.mask_key(cls.SUNO_API_KEY), "value": cls.SUNO_API_KEY},
            "suno_base_url": {"set": bool(cls.SUNO_API_BASE_URL), "masked": cls.SUNO_API_BASE_URL, "value": cls.SUNO_API_BASE_URL},
            "music_provider": {"set": bool(cls.MUSIC_PROVIDER), "masked": cls.MUSIC_PROVIDER, "value": cls.MUSIC_PROVIDER},
            "music_gemini_model": {"set": bool(cls.MUSIC_GEMINI_MODEL), "masked": cls.MUSIC_GEMINI_MODEL, "value": cls.MUSIC_GEMINI_MODEL},
            "music_gemini_base_url": {"set": bool(cls.MUSIC_GEMINI_BASE_URL), "masked": cls.MUSIC_GEMINI_BASE_URL, "value": cls.MUSIC_GEMINI_BASE_URL},
            "music_gemini_project_id": {"set": bool(cls.MUSIC_GEMINI_PROJECT_ID), "masked": cls.MUSIC_GEMINI_PROJECT_ID, "value": cls.MUSIC_GEMINI_PROJECT_ID},
            "music_gemini_location": {"set": bool(cls.MUSIC_GEMINI_LOCATION), "masked": cls.MUSIC_GEMINI_LOCATION, "value": cls.MUSIC_GEMINI_LOCATION},
            "typecast": {"set": bool(cls.TYPECAST_API_KEY), "masked": cls.mask_key(cls.TYPECAST_API_KEY), "value": cls.TYPECAST_API_KEY},
            "google_cloud": {"set": bool(cls.GOOGLE_APPLICATION_CREDENTIALS), "masked": cls.mask_key(cls.GOOGLE_APPLICATION_CREDENTIALS), "value": cls.GOOGLE_APPLICATION_CREDENTIALS},
            "openai": {"set": bool(cls.OPENAI_API_KEY), "masked": cls.mask_key(cls.OPENAI_API_KEY), "value": cls.OPENAI_API_KEY},
            "topview": {"set": bool(cls.TOPVIEW_API_KEY), "masked": cls.mask_key(cls.TOPVIEW_API_KEY), "value": cls.TOPVIEW_API_KEY},
            "topview_uid": {"set": bool(cls.TOPVIEW_UID), "masked": cls.mask_key(cls.TOPVIEW_UID), "value": cls.TOPVIEW_UID}
        }

    @classmethod
    def youtube_api_keys(cls):
        """Return unique YouTube keys in primary-then-fallback order."""
        import re
        keys = []
        for value in (cls.YOUTUBE_API_KEY, cls.YOUTUBE_API_KEYS):
            for key in re.split(r"[,;\r\n]+", str(value or "")):
                key = key.strip()
                if key and key not in keys:
                    keys.append(key)
        return keys


    @classmethod
    def get_kst_time(cls):
        """한국 표준시(KST) 현재 시간 반환"""
        from datetime import datetime, timezone, timedelta
        kst = timezone(timedelta(hours=9))
        return datetime.now(kst)

config = Config()
config.setup_directories()
