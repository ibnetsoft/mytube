"""
대본(script) 생성 시 사용할 "글쓰기 스타일 지침"을 단일 지점에서 해석하는 공통 계층.

문제 배경 (AIR-????): 수동 대본 기획/생성 경로(app/routers/gemini.py,
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

"default"(또는 미지정) 스타일은 의도적으로 빈 지침("")을 반환한다. DB의 "default"
프리셋 값은 실제로는 촬영/색감 등 영상미 설명(예: "[자연스럽고 선명한 색감],
[깨끗하고 투명한 화질]...")이라 글쓰기 지침으로 삽입하면 의미가 없기 때문이며,
이는 autopilot_service.py가 이전부터 `if style_key != "default":` 조건으로
지침 삽입을 건너뛰던 기존 동작과도 일치한다.
"""

from typing import Optional

import database as db

_NEUTRAL_KEYS = {"", "default", "none"}


def _log(requested: str, resolved: str, fallback_used: bool, db_error: bool) -> None:
    # 요청/실사용 스타일 키, 폴백 여부만 남긴다. 프롬프트 전문이나 대본 원문은 기록하지 않는다.
    print(
        f"[ScriptStyleResolver] requested={requested or '(none)'} "
        f"resolved={resolved} fallback_used={fallback_used} db_error={db_error}"
    )


def resolve_script_style_directive(script_style: Optional[str]) -> str:
    """script_style 코드를 AI 프롬프트에 바로 삽입 가능한 지침 문자열로 변환한다.

    반환값:
    - "" : 스타일 지침을 추가하지 말 것 (기본/미지정/알수없음/비활성/DB 조회 실패 시 전부 이 값)
    - "[Writing Style Directive]\\n...\\nApply this style strictly throughout the script."
      : 유효한 스타일이 확인된 경우

    호출부는 다음과 같이 사용한다:
        directive = resolve_script_style_directive(style_key)
        if directive:
            prompt += f"\\n\\n{directive}"
    """
    requested = (script_style or "").strip().lower()

    if requested in _NEUTRAL_KEYS:
        _log(requested, "default", fallback_used=False, db_error=False)
        return ""

    try:
        presets = db.get_script_style_presets()
    except Exception as e:
        print(f"[ScriptStyleResolver] preset lookup failed: {e}")
        _log(requested, "default", fallback_used=True, db_error=True)
        return ""

    prompt_value = (presets.get(requested) or "").strip()
    if not prompt_value:
        # 존재하지 않는 스타일 키이거나, 프리셋은 있으나 내용이 비어있는(=사실상 비활성) 경우.
        # script_style_presets 테이블에는 별도 is_active 컬럼이 없어 "빈 prompt_value"를
        # 비활성 상태의 대용 지표로 취급한다.
        _log(requested, "default", fallback_used=True, db_error=False)
        return ""

    _log(requested, requested, fallback_used=False, db_error=False)
    return (
        f"[Writing Style Directive]\n{prompt_value}\n"
        "Apply this style strictly throughout the script."
    )
