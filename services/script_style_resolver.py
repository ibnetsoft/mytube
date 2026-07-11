"""
대본(script) 생성 시 사용할 "글쓰기 스타일 지침"을 단일 지점에서 해석하는 공통 계층.

문제 배경: 수동 대본 기획/생성 경로(app/routers/gemini.py,
templates/pages/script_gen.html)는 script_style을 전혀 프롬프트에 반영하지 않았고,
autopilot 경로(services/autopilot_service.py)는 자체적으로 DB 프리셋을 조회해
스타일 지침을 조립하는 로직을 중복 구현하고 있었다. 이 모듈은 두 경로가 동일한
스타일 해석 결과를 사용하도록 단일 진입점을 제공한다.

스타일 데이터 소스: SQLite `script_style_presets` 테이블
(database.get_script_style_presets), 웹어드민 Settings > 대본 스타일 프롬프트
설정 화면(/api/settings/script-style-presets)이 관리하는 바로 그 테이블이다.
(참고: services/settings_service.py의 data/settings.json "script_styles" 키는
별도의 레거시 시스템으로, 실제 생성 경로 어디에서도 사용되지 않는 죽은 데이터라
이번 통합 대상에서 제외했다.)

[정책 변경] "default"(또는 미지정) 스타일도 이제 실제 글쓰기 지침을 반환한다.
과거에는 DB의 "default" 프리셋이 실제로는 색감/화질 등 영상미 설명이라 빈
문자열을 반환했으나, docs/script_style_preset_audit.md의 1차 정비를 통해
"default" 프리셋 자체를 진짜 글쓰기 지침으로 교체했다. DB에 접근할 수 없거나
"default" 프리셋이 비어있는 극단적인 경우에도 생성이 끊기지 않도록
_BUILTIN_DEFAULT_DIRECTIVE로 안전하게 폴백한다.

[별칭 정책] 과거 여러 세대에 걸쳐 동일한 내용이 서로 다른 키 이름으로 중복
저장된 항목이 있다 (예: joseon_sageuk/joseon_drama). 기존에 저장된 프로젝트나
topics_queue 행이 레거시 키를 참조하고 있어도 계속 정상 동작하도록, 레거시 키는
_ALIAS_MAP을 통해 canonical 키로 변환한 뒤 canonical 프리셋 내용을 사용한다.
DB에서 레거시 키 자체를 삭제하지는 않는다 (docs/script_style_canonical_map.md 참조).
"""

import datetime
import threading
from typing import Optional

import database as db

_NEUTRAL_KEYS = {"", "default", "none"}

# 레거시 키 -> canonical 키. canonical 쪽은 services/i18n.py 및
# auth-web/app/api/admin/topics-queue/route.ts의 SCRIPT_STYLE_KEYS 허용목록에
# 실제로 노출되는 키를 그대로 채택했다 (근거: docs/script_style_canonical_map.md).
_ALIAS_MAP = {
    "joseon_drama": "joseon_sageuk",
    "north_korea_drama": "north_korean_drama",
    "silent_film_20s": "silent_20s",
    "k_comics": "k_manhwa",
    "cute_animal": "cute_animal_char",
    "neon_citypop": "neonsign_citypop",
    "pencil_sketch": "graphite_sketch",
    "renaissance_religious": "renaissance_sacred",
    "bgm_focus": "bgm",
    "old_story": "story",
}

# DB에 전혀 접근할 수 없거나 "default" 프리셋이 비어있는 경우에도 생성이
# 중단되지 않도록 사용하는 내장 안전 지침. (script_style_presets 테이블은
# 관리자가 실수로 비울 수 있는 사용자 데이터이므로 최후의 방어선이 필요하다.)
_BUILTIN_DEFAULT_DIRECTIVE = (
    "자연스럽고 명확한 한국어로 작성한다. 같은 정보나 표현을 불필요하게 반복하지 않는다. "
    "각 섹션은 주어진 목적(도입/전개/결말 등)에 맞는 내용만 담는다. "
    "앞 섹션과 자연스럽게 이어지도록 문맥을 연결한다. 지정된 나레이션 모드(1인 독백 또는 "
    "대화)를 그대로 지킨다. \"이 영상에서는\", \"오늘 소개할 내용은\" 같은 과도한 메타 설명이나 "
    "자기소개성 문장을 반복하지 않는다."
)

_log_lock = threading.Lock()
_last_logged_key = None  # 동일 스타일 반복 로그(섹션별 다회 호출) 억제용


def _write_log_line(line: str) -> None:
    """print + debug.log 파일 기록을 각각 독립적으로 방어한다.

    services/autopilot_service.py의 log_debug()와 동일한 패턴(파일 로그 백업)을
    쓰되, print() 자체도 try/except로 감싼다: console=False로 패키징된 Windows
    빌드는 sys.stdout이 None이거나 아무것도 받지 않는 더미 스트림일 수 있고,
    거기에 그대로 print()하면 AttributeError 등으로 대본 생성 자체가 죽을 수
    있다. 로그 실패가 생성 실패로 번지는 일이 없도록 각 단계를 개별적으로
    swallow한다. 로그 내용은 스타일 키/불리언뿐이라(ASCII) cp949 인코딩
    문제는 애초에 발생하지 않는다.
    """
    try:
        print(line)
    except Exception:
        pass
    try:
        from config import config
        with open(config.DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] {line}\n")
    except Exception:
        pass


def _log(requested_style: str, resolved_style: str, fallback_used: bool, db_error: bool) -> None:
    global _last_logged_key
    key = (requested_style or "(none)", resolved_style, fallback_used, db_error)
    with _log_lock:
        if key == _last_logged_key:
            # 대본 한 편은 섹션마다(많게는 수십 번) 같은 script_style로 이 함수를
            # 반복 호출한다. 매번 동일한 내용을 다시 남기면 debug.log가 금방
            # 의미 없는 반복으로 채워지므로, 직전과 완전히 같은 결과는 생략한다.
            # (동시 요청이 우연히 같은 조합을 내면 그 사이의 로그 한 줄이 생략될
            # 수 있으나, 이 로그는 감사 기록이 아니라 진단용이라 감수 가능한 트레이드오프.)
            return
        _last_logged_key = key
    _write_log_line(
        f"[ScriptStyleResolver] requested_style={key[0]} resolved_style={resolved_style} "
        f"fallback_used={fallback_used} db_error={db_error}"
    )


def _wrap_directive(prompt_value: str) -> str:
    return (
        f"[Writing Style Directive]\n{prompt_value}\n"
        "Apply this style strictly throughout the script."
    )


def resolve_script_style_directive(script_style: Optional[str]) -> str:
    """script_style 코드를 AI 프롬프트에 바로 삽입 가능한 지침 문자열로 변환한다.

    항상 비어있지 않은 문자열을 반환한다 (default/미지정/알수없음/비활성/DB 조회
    실패 시에도 최소한 기본 글쓰기 지침을 반환한다 - _BUILTIN_DEFAULT_DIRECTIVE 참고).

    호출부는 다음과 같이 사용한다:
        directive = resolve_script_style_directive(style_key)
        if directive:
            prompt += f"\\n\\n{directive}"
    """
    requested = (script_style or "").strip().lower()
    canonical = _ALIAS_MAP.get(requested, requested)

    if canonical in _NEUTRAL_KEYS:
        directive, db_error = _resolve_default(db_error=False)
        _log(requested, "default", fallback_used=False, db_error=db_error)
        return directive

    try:
        presets = db.get_script_style_presets()
    except Exception as e:
        _write_log_line(f"[ScriptStyleResolver] preset lookup failed: {e}")
        directive, db_error = _resolve_default(db_error=True)
        _log(requested, "default", fallback_used=True, db_error=True)
        return directive

    prompt_value = (presets.get(canonical) or "").strip()
    if not prompt_value:
        # 존재하지 않는 스타일 키이거나, 프리셋은 있으나 내용이 비어있는(=사실상 비활성)
        # 경우. script_style_presets 테이블에는 별도 is_active 컬럼이 없어 "빈
        # prompt_value"를 비활성 상태의 대용 지표로 취급한다.
        directive, db_error = _resolve_default(db_error=False, presets=presets)
        _log(requested, "default", fallback_used=True, db_error=db_error)
        return directive

    _log(requested, canonical, fallback_used=False, db_error=False)
    return _wrap_directive(prompt_value)


def _resolve_default(db_error: bool, presets: Optional[dict] = None) -> tuple[str, bool]:
    """"default" 지침을 해석한다. DB의 default 프리셋을 우선 사용하고,
    DB 접근 실패/빈 값이면 내장 지침으로 폴백한다.
    반환: (directive, db_error_occurred)
    """
    if db_error:
        return _wrap_directive(_BUILTIN_DEFAULT_DIRECTIVE), True

    try:
        if presets is None:
            presets = db.get_script_style_presets()
    except Exception as e:
        _write_log_line(f"[ScriptStyleResolver] default preset lookup failed: {e}")
        return _wrap_directive(_BUILTIN_DEFAULT_DIRECTIVE), True

    default_value = (presets.get("default") or "").strip()
    if not default_value:
        return _wrap_directive(_BUILTIN_DEFAULT_DIRECTIVE), False
    return _wrap_directive(default_value), False
