"""
Voicebox TTS 공용 클라이언트 (스튜디오 / AIR Worker 양쪽에서 사용)

Voicebox(https://docs.voicebox.sh)는 로컬 우선 오픈소스 TTS 서버로,
MSI 설치 시 http://127.0.0.1:17493 에서 자동 실행된다 (인증 없음 - 로컬/신뢰 네트워크 전용).

주요 엔드포인트:
  - GET  /health                     서버/GPU/모델 상태
  - GET  /profiles                   음성 프로필 목록
  - GET  /profiles/presets/{engine}  엔진별 프리셋 보이스 (qwen_custom_voice에 한국어 Sohee 존재)
  - POST /profiles                   프리셋 기반 프로필 생성 (voice_type="preset")
  - POST /generate/stream            TTS 생성 - 요청 JSON을 받아 WAV 바이트 스트림 반환
  - GET  /models/status              엔진 모델 다운로드/로드 상태
  - POST /models/download            모델 다운로드 트리거

이 모듈은 config.py를 import하지 않고 환경변수를 직접 읽는다 -
워커 프로세스(단일 exe)에서도 services 경로만 있으면 동작하도록 하기 위함.

음성 참조(voice_ref) 형식 (프론트엔드/잡 페이로드 공통):
  - "profile:<profile_id>"          기존 Voicebox 프로필
  - "preset:<engine>:<voice_id>"    프리셋 보이스 (최초 사용 시 프로필 자동 생성)
"""
import asyncio
import os
import re
import subprocess
import tempfile
from typing import Callable, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# 설정 (env 기반 - config.py 의존 없음)
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "http://127.0.0.1:17493"
DEFAULT_ENGINE = os.getenv("VOICEBOX_ENGINE", "qwen")
DEFAULT_MODEL_SIZE = os.getenv("VOICEBOX_MODEL_SIZE", "1.7B")
GENERATE_TIMEOUT = float(os.getenv("VOICEBOX_TIMEOUT", "900"))  # CPU TTS는 장문일 경우 수 분 소요

# engine 파라미터 정의: ^(qwen|qwen_custom_voice|luxtts|chatterbox|chatterbox_turbo|tada|kokoro)$
ENGINE_INFO: Dict[str, dict] = {
    "qwen": {"label": "Qwen3-TTS (제로샷 클론)", "korean": True, "model": "qwen-tts"},
    "qwen_custom_voice": {"label": "Qwen CustomVoice (한국어 프리셋)", "korean": True, "model": "qwen-custom-voice"},
    "luxtts": {"label": "LuxTTS (경량/CPU 친화적)", "korean": False, "model": "luxtts"},
    "chatterbox": {"label": "Chatterbox Multilingual", "korean": False, "model": "chatterbox"},
    "chatterbox_turbo": {"label": "Chatterbox Turbo (영어)", "korean": False, "model": "chatterbox"},
    "tada": {"label": "HumeAI TADA", "korean": True, "model": "tada"},
    "kokoro": {"label": "Kokoro 82M (초경량)", "korean": False, "model": "kokoro"},
}

# Voicebox generation language 허용값
ALLOWED_LANGUAGES = {
    "zh", "en", "ja", "ko", "de", "fr", "ru", "pt", "es", "it",
    "he", "ar", "da", "el", "fi", "hi", "ms", "nl", "no", "pl", "sv", "sw", "tr",
}

# BCP47/Full 코드 -> Voicebox 2자리 코드
LANGUAGE_MAP = {
    "ko": "ko", "ko-kr": "ko", "ko_kr": "ko", "korean": "ko",
    "en": "en", "en-us": "en", "en_us": "en", "en-gb": "en", "english": "en",
    "ja": "ja", "ja-jp": "ja", "ja_jp": "ja", "japanese": "ja",
    "zh": "zh", "zh-cn": "zh", "zh_cn": "zh", "chinese": "zh",
    "de": "de", "fr": "fr", "ru": "ru", "pt": "pt", "es": "es", "it": "it",
    "he": "he", "ar": "ar", "da": "da", "el": "el", "fi": "fi", "hi": "hi",
    "ms": "ms", "nl": "nl", "no": "no", "pl": "pl", "sv": "sv", "sw": "sw", "tr": "tr",
}


def map_language(lang: Optional[str]) -> str:
    """'ko-KR'/'ko_KR'/'Korean' 등을 Voicebox 언어 코드('ko')로 변환. 알 수 없으면 'ko'."""
    key = str(lang or "").strip().lower()
    if key in LANGUAGE_MAP:
        return LANGUAGE_MAP[key]
    prefix = key.split("-")[0].split("_")[0]
    return LANGUAGE_MAP.get(prefix, "ko")


def get_base_url() -> str:
    return (os.getenv("VOICEBOX_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def model_name_for(engine: str, model_size: Optional[str] = None) -> Optional[str]:
    """엔진 + 모델 크기 -> GET /models/status 의 model_name."""
    engine = (engine or "").strip()
    size = (model_size or os.getenv("VOICEBOX_MODEL_SIZE") or DEFAULT_MODEL_SIZE).strip()
    if engine == "qwen":
        return f"qwen-tts-{size}" if size in ("0.6B", "1.7B") else "qwen-tts-1.7B"
    if engine == "qwen_custom_voice":
        return f"qwen-custom-voice-{size}" if size in ("0.6B", "1.7B") else "qwen-custom-voice-1.7B"
    if engine == "luxtts":
        return "luxtts"
    if engine == "chatterbox":
        return "chatterbox-tts"
    if engine == "chatterbox_turbo":
        return "chatterbox-turbo"
    if engine == "tada":
        # 1B는 영어 전용, 멀티링구얼(한국어 포함)은 3B-ml
        return "tada-3b-ml" if map_language(os.getenv("VOICEBOX_LANGUAGE", "ko")) != "en" else "tada-1b"
    if engine == "kokoro":
        return "kokoro"
    return None


class VoiceboxError(Exception):
    """Voicebox API 호출 실패 (한국어 사용자 안내용 메시지)."""


class VoiceboxConnectionError(VoiceboxError):
    """Voicebox 서버에 연결 자체가 안 되는 경우."""


_CONNECTION_HINT = (
    "Voicebox 서버({base})에 연결할 수 없습니다. "
    "Voicebox 앱이 실행 중인지, 포트(기본 17493)가 맞는지 확인해주세요."
)


class VoiceboxClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 15.0):
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # 내부 공통 요청
    # ------------------------------------------------------------------
    async def _request(
        self, method: str, path: str, *, json_body: dict = None,
        timeout: Optional[float] = None, stream: bool = False,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=timeout or self.timeout, trust_env=False, follow_redirects=True
            ) as client:
                if stream:
                    return await client.send(
                        client.build_request(method, url, json=json_body), stream=True
                    )
                return await client.request(method, url, json=json_body)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as e:
            raise VoiceboxConnectionError(_CONNECTION_HINT.format(base=self.base_url)) from e
        except httpx.HTTPError as e:
            raise VoiceboxError(f"Voicebox API 요청 실패 ({path}): {e}") from e

    @staticmethod
    def _raise_for_status(response: httpx.Response, path: str):
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = body.get("detail") or body.get("error") or response.text[:300]
            except Exception:
                detail = response.text[:300]
            raise VoiceboxError(f"Voicebox API 오류 ({path}, {response.status_code}): {detail}")

    # ------------------------------------------------------------------
    # 상태 / 프로필 / 모델
    # ------------------------------------------------------------------
    async def check_health(self) -> dict:
        resp = await self._request("GET", "/health")
        self._raise_for_status(resp, "/health")
        return resp.json()

    async def list_profiles(self) -> List[dict]:
        resp = await self._request("GET", "/profiles")
        self._raise_for_status(resp, "/profiles")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def list_presets(self, engine: str) -> List[dict]:
        resp = await self._request("GET", f"/profiles/presets/{engine}")
        self._raise_for_status(resp, f"/profiles/presets/{engine}")
        data = resp.json()
        voices = data.get("voices") if isinstance(data, dict) else data
        return voices if isinstance(voices, list) else []

    async def ensure_preset_profile(self, engine: str, preset_voice_id: str, language: str = "ko") -> dict:
        """프리셋 보이스를 생성에 사용 가능한 프로필로 변환한다.

        동일 프리셋(engine + voice_id)의 프로필이 이미 있으면 재사용하고,
        없으면 POST /profiles 로 자동 생성한다 (voice_type="preset").
        """
        profiles = await self.list_profiles()
        for p in profiles:
            if p.get("preset_engine") == engine and p.get("preset_voice_id") == preset_voice_id:
                return p

        preset_name = preset_voice_id.replace("_", " ").strip() or preset_voice_id
        body = {
            "name": f"AIR {engine} {preset_name}"[:100],
            "voice_type": "preset",
            "preset_engine": engine,
            "preset_voice_id": preset_voice_id,
            "language": map_language(language),
        }
        resp = await self._request("POST", "/profiles", json_body=body)
        self._raise_for_status(resp, "/profiles")
        return resp.json()

    async def resolve_voice_ref(
        self, voice_ref: str, default_engine: Optional[str] = None, language: str = "ko"
    ) -> dict:
        """voice_ref -> {"profile_id", "engine", "language"}.

        - "profile:<id>"  : 기존 프로필 조회 (없으면 오류)
        - "preset:<engine>:<voice_id>" : 프로필 자동 생성/재사용
        - 그 외(빈 값 등)  : 기본 엔진 + 첫 번째 프리셋/프로필로 폴백
        """
        ref = str(voice_ref or "").strip()
        engine = default_engine or DEFAULT_ENGINE

        if ref.startswith("profile:"):
            profile_id = ref[len("profile:"):].strip()
            profiles = await self.list_profiles()
            for p in profiles:
                if p.get("id") == profile_id:
                    return {
                        "profile_id": profile_id,
                        "engine": p.get("default_engine") or engine,
                        "language": p.get("language") or map_language(language),
                        "name": p.get("name"),
                    }
            raise VoiceboxError(f"Voicebox 프로필을 찾을 수 없습니다: {profile_id}")

        if ref.startswith("preset:"):
            parts = ref.split(":", 2)
            if len(parts) != 3 or not parts[2]:
                raise VoiceboxError(f"프리셋 참조 형식이 잘못되었습니다: {ref} (preset:<engine>:<voice_id>)")
            _, engine, preset_voice_id = parts
            profile = await self.ensure_preset_profile(engine, preset_voice_id, language)
            return {
                "profile_id": profile["id"],
                "engine": engine,
                "language": profile.get("language") or map_language(language),
                "name": profile.get("name"),
            }

        # 폴백: 기존 프로필 -> 엔진 기본 프리셋 순
        profiles = await self.list_profiles()
        if profiles:
            p = profiles[0]
            return {
                "profile_id": p["id"],
                "engine": p.get("default_engine") or engine,
                "language": p.get("language") or map_language(language),
                "name": p.get("name"),
            }
        presets = await self.list_presets(engine)
        if presets:
            v = presets[0]
            profile = await self.ensure_preset_profile(engine, v["voice_id"], language)
            return {
                "profile_id": profile["id"],
                "engine": engine,
                "language": profile.get("language") or map_language(language),
                "name": profile.get("name"),
            }
        raise VoiceboxError(
            "사용 가능한 Voicebox 음성이 없습니다. Voicebox 앱에서 보이스를 만들거나 프리셋을 선택해주세요."
        )

    # ------------------------------------------------------------------
    # 생성
    # ------------------------------------------------------------------
    async def generate_stream(
        self, text: str, profile_id: str, engine: Optional[str] = None,
        language: str = "ko", seed: Optional[int] = None, timeout: Optional[float] = None,
    ) -> bytes:
        """POST /generate/stream - WAV 바이트 반환 (ElevenLabs 대체용 기본 경로)."""
        body = {
            "profile_id": profile_id,
            "text": str(text or "").strip(),
            "language": map_language(language),
            "engine": engine or DEFAULT_ENGINE,
            "model_size": os.getenv("VOICEBOX_MODEL_SIZE") or DEFAULT_MODEL_SIZE,
        }
        if seed is not None:
            body["seed"] = int(seed)

        if not body["text"]:
            raise VoiceboxError("TTS를 생성할 텍스트가 비어 있습니다.")
        if len(body["text"]) > 50000:
            raise VoiceboxError("텍스트가 너무 깁니다 (최대 50,000자).")

        resp = await self._request(
            "POST", "/generate/stream", json_body=body,
            timeout=timeout or GENERATE_TIMEOUT,
        )
        self._raise_for_status(resp, "/generate/stream")
        content = resp.content
        if not content:
            raise VoiceboxError("Voicebox가 빈 오디오를 반환했습니다.")
        return content

    # ------------------------------------------------------------------
    # 모델 관리
    # ------------------------------------------------------------------
    async def list_models(self) -> List[dict]:
        resp = await self._request("GET", "/models/status")
        self._raise_for_status(resp, "/models/status")
        data = resp.json()
        models = data.get("models") if isinstance(data, dict) else data
        return models if isinstance(models, list) else []

    async def start_model_download(self, model_name: str) -> dict:
        resp = await self._request("POST", "/models/download", json_body={"model_name": model_name})
        self._raise_for_status(resp, "/models/download")
        return resp.json()


# 싱글톤 (스튜디오 라우터용)
voicebox_client = VoiceboxClient()


# ---------------------------------------------------------------------------
# 오디오 후처리 (WAV -> MP3 변환 / 속도 / 병합) - 스튜디오/워커 공용
# ---------------------------------------------------------------------------
def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _run_hidden(cmd: list):
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True, startupinfo=startupinfo,
    )


def wav_to_mp3(wav_path: str, mp3_path: str, speed: float = 1.0) -> str:
    """WAV 파일을 MP3로 변환. speed != 1.0이면 atempo로 속도 조절 (한 번의 ffmpeg 패스)."""
    speed = max(0.5, min(2.0, float(speed or 1.0)))
    cmd = [_ffmpeg_exe(), "-y", "-i", wav_path]
    if abs(speed - 1.0) > 0.001:
        cmd += ["-filter:a", f"atempo={speed:.3f}"]
    cmd += ["-c:a", "libmp3lame", "-q:a", "2", mp3_path]
    _run_hidden(cmd)
    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
        raise VoiceboxError(f"MP3 변환에 실패했습니다: {mp3_path}")
    return mp3_path


def wav_bytes_to_mp3(wav_bytes: bytes, mp3_path: str, speed: float = 1.0) -> str:
    """Voicebox 응답(WAV bytes)을 임시 파일에 쓰고 MP3로 변환한다."""
    fd, tmp_wav = tempfile.mkstemp(suffix=".wav", prefix="voicebox_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(wav_bytes)
        return wav_to_mp3(tmp_wav, mp3_path, speed)
    finally:
        try:
            os.remove(tmp_wav)
        except OSError:
            pass


def merge_audio_files(audio_files: List[str], output_path: str) -> bool:
    """세그먼트 MP3들을 하나로 병합 (pydub 1차, MoviePy 폴백). tts.py 검증 로직과 동일."""
    try:
        from pydub import AudioSegment
        import imageio_ffmpeg
        AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

        combined = AudioSegment.empty()
        for af in audio_files:
            combined += AudioSegment.from_file(af)
        combined.export(output_path, format="mp3")
        return True
    except Exception as pydub_err:
        print(f"[Voicebox] pydub 병합 실패 ({pydub_err}), MoviePy로 재시도합니다.")

    try:
        try:
            from moviepy import AudioFileClip, concatenate_audioclips
        except ImportError:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
            from moviepy.audio.AudioClip import concatenate_audioclips

        clips = [AudioFileClip(af) for af in audio_files]
        try:
            final_clip = concatenate_audioclips(clips)
            final_clip.write_audiofile(output_path, codec="libmp3lame", logger=None)
        finally:
            for c in clips:
                try:
                    c.close()
                except Exception:
                    pass
        return True
    except Exception as moviepy_err:
        print(f"[Voicebox] MoviePy 병합 실패: {moviepy_err}")
        return False


def audio_duration_seconds(path: str) -> float:
    """오디오 길이(초) 계산.

    pydub은 ffprobe가 필요한데 데스크톱 번들 환경(imageio_ffmpeg)에는 없다
    (tts.py의 기존 검증 결과와 동일) - MoviePy 폴백을 둔다.
    """
    try:
        from pydub import AudioSegment
        try:
            import imageio_ffmpeg
            AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
        return AudioSegment.from_file(path).duration_seconds
    except Exception:
        pass
    try:
        try:
            from moviepy import AudioFileClip
        except ImportError:
            from moviepy.audio.io.AudioFileClip import AudioFileClip
        with AudioFileClip(path) as clip:
            return float(clip.duration)
    except Exception:
        pass
    try:
        import wave
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# 대본 세그먼트 파싱 - "이름: 대사" 멀티보이스 규칙 (app/routers/tts.py 와 동일)
# ---------------------------------------------------------------------------
_SPEAKER_PATTERN = re.compile(
    r'^\s*(?:'
    r'[\*\_\[\(]*([^\s:\[\(\*\_]+)[\*\_\]\)]*[ \t]*(\([^)]*\))?[ \t]*[:：][ \t]*(.*)'
    r'|'
    r'([^\s:\[\(\*\_]+)[ \t]*[\)）\]][ \t]*(.*)'
    r')$'
)


def parse_speaker_segments(text: str) -> List[dict]:
    """대본을 [{"speaker": 이름, "text": 대사}] 세그먼트로 파싱. 화자 없는 줄은 이전 화자에 귀속."""
    segments: List[dict] = []
    current_chunk: List[str] = []
    current_speaker: Optional[str] = None

    for line in str(text or "").split("\n"):
        match = _SPEAKER_PATTERN.match(line.strip())
        if match:
            if current_chunk:
                segments.append({"speaker": current_speaker, "text": "\n".join(current_chunk)})
            if match.group(1) is not None:
                current_speaker = match.group(1).strip()
                emotion = match.group(2) or ""
                content = match.group(3).strip()
            else:
                current_speaker = match.group(4).strip()
                emotion = ""
                content = match.group(5).strip()
            current_speaker = re.sub(r'[\*\_\#\[\]\(\)]', '', current_speaker).strip()
            if emotion:
                content = f"{emotion} {content}"
            current_chunk = [content]
        else:
            current_chunk.append(line.strip())

    if current_chunk:
        segments.append({"speaker": current_speaker, "text": "\n".join(current_chunk)})
    return segments


# ---------------------------------------------------------------------------
# 동기 컨텍스트용 헬퍼 (AIR Worker render_audio 잡에서 사용)
# ---------------------------------------------------------------------------
def _resolve_and_generate_mp3(
    client: VoiceboxClient, text: str, voice_ref: str, mp3_path: str,
    engine: Optional[str], language: str, speed: float, seed: Optional[int],
) -> dict:
    """[내부] 단일 세그먼트: voice_ref 해석 -> /generate/stream -> MP3 저장."""
    resolved = asyncio.run(
        client.resolve_voice_ref(voice_ref, default_engine=engine, language=language)
    )
    wav_bytes = asyncio.run(
        client.generate_stream(
            text, resolved["profile_id"], engine=resolved["engine"],
            language=language, seed=seed,
        )
    )
    wav_bytes_to_mp3(wav_bytes, mp3_path, speed)
    return {
        "audio_path": mp3_path,
        "profile_id": resolved["profile_id"],
        "engine": resolved["engine"],
        "duration": audio_duration_seconds(mp3_path),
    }


def generate_voicebox_audio_sync(
    text: str,
    voice_ref: str,
    output_path: str,
    engine: Optional[str] = None,
    language: str = "ko",
    speed: float = 1.0,
    seed: Optional[int] = None,
    multi_voice: bool = False,
    voice_map: Optional[Dict[str, str]] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """워커(동기 컨텍스트)용 TTS 생성 엔트리.

    - 단일 모드: 전체 텍스트를 한 번에 생성
    - 멀티보이스 모드: "이름: 대사" 파싱 후 화자별 voice_ref 로 세그먼트 생성 -> 병합
    반환: {"audio_path", "duration", "engine", "profile_id", "segments": n}
    """
    client = VoiceboxClient()
    lang = map_language(language)
    voice_map = voice_map or {}

    if not multi_voice:
        result = _resolve_and_generate_mp3(
            client, text, voice_ref, output_path, engine, lang, speed, seed
        )
        if progress_cb:
            progress_cb(100, "TTS 생성 완료")
        result["segments"] = 1
        return result

    segments = parse_speaker_segments(text)
    if not segments:
        raise VoiceboxError("멀티보이스로 처리할 대본 세그먼트가 없습니다.")
    if segments and not any(voice_map.get(s["speaker"]) for s in segments):
        # 화자 매핑이 전혀 없으면 단일 보이스로 폴백
        return generate_voicebox_audio_sync(
            text, voice_ref, output_path, engine, lang, speed, seed,
            multi_voice=False, progress_cb=progress_cb,
        )

    base, _ext = os.path.splitext(output_path)
    seg_files: List[str] = []
    last_engine = engine or DEFAULT_ENGINE
    last_profile = ""
    try:
        total = len(segments)
        for idx, seg in enumerate(segments):
            ref = voice_map.get(seg["speaker"]) or voice_ref
            seg_path = f"{base}_seg_{idx:03d}.mp3"
            r = _resolve_and_generate_mp3(
                client, seg["text"], ref, seg_path, engine, lang, speed, seed
            )
            seg_files.append(r["audio_path"])
            last_engine = r["engine"]
            last_profile = r["profile_id"]
            if progress_cb:
                pct = int((idx + 1) / total * 90)
                progress_cb(pct, f"TTS 세그먼트 {idx + 1}/{total} 완료")

        if len(seg_files) == 1:
            os.replace(seg_files[0], output_path)
        elif not merge_audio_files(seg_files, output_path):
            raise VoiceboxError("오디오 세그먼트 병합에 실패했습니다 (pydub/MoviePy 모두 실패).")
    finally:
        for f in seg_files:
            if os.path.exists(f) and f != output_path:
                try:
                    os.remove(f)
                except OSError:
                    pass

    if progress_cb:
        progress_cb(95, "오디오 병합 완료")
    return {
        "audio_path": output_path,
        "duration": audio_duration_seconds(output_path),
        "engine": last_engine,
        "profile_id": last_profile,
        "segments": len(segments),
    }
