"""Load the centrally managed Japanese historical-fidelity writing guideline."""
from __future__ import annotations

import threading
import time
from typing import Any

GUIDELINE_KEY = "prompt_guideline_japanese_period_fidelity"
_CACHE_SECONDS = 300
_cached_value = ""
_cached_at = 0.0
_lock = threading.Lock()

# Fail closed if the shared setting is temporarily unavailable. The complete,
# editable source of truth is the global_settings row named by GUIDELINE_KEY.
_SAFE_FALLBACK = """[일본 시대·문화 고증 지침]
- 적용 범위: 배경 국가가 일본이거나 카테고리가 日本昔話인 모든 기획·자막 분석·대본·장면/이미지 프롬프트·최종 검수 단계.
- 근거 우선순위: 사용자가 명시한 설정과 자막에서 직접 확인한 원전 정보를 보존한다. 영상의 줄거리만 각색하고 시대·지역 변경은 사용자가 요청한 경우에만 한다.
- 자막 분석: 줄거리 요약과 별도로 시대·지역·인물 관계·직책/신분·풍습·복식·음식·건축·물건·교통수단을 추출한다. 직접 확인한 사실, 사용자 설정, 추론, 알 수 없음으로 나누고, 구체 설정에는 원문 짧은 인용을 붙인다. 자막이 허구의 민담이면 허구 속 설정과 실제 역사 사실을 구분한다.
- 시대 미상: 일본 민담이라는 이유만으로 에도·헤이안 등 특정 시대를 추정하지 않는다. 시대가 불명확하거나 출처가 뒷받침하지 않으면 연도·지역·관직·신분·복식·풍습·생활용품을 새로 단정하지 말고, 원문을 유지하거나 시대 중립적인 쉬운 일본어로 쓴다.
- 언어와 생활상: 확인된 시대·지역에서 사용 가능한 일본어 어휘와 호칭을 고른다. 근거 없는 사극 말투, 현대 유행어·기관·기술·물품을 피한다. 정확한 옛말을 확신할 수 없으면 과장된 고어 대신 자연스럽고 시대 중립적인 표현을 택한다.
- 과잉 연출 금지: 현대 일본 배경에 기모노·신사·성 같은 전통 소재를 강제로 넣지 않는다. 일본이라는 국적만으로 인물의 성격·직업·관계를 전형화하지 않는다. 이미지 프롬프트도 대본의 확정된 시대·지역·소품과 일치시킨다.
- 최종 검수: 모든 구체적인 시대·지역·관직·신분·풍습·복식·음식·건물·물건·교통 묘사를 원문 근거나 사용자 설정과 대조한다. 근거 없는 세부는 삭제하거나 중립화하고, 해결되지 않은 시대착오·구체 주장·설정 충돌이 남으면 통과시키지 않는다. 검수 결과에 대조 근거와 수정 항목을 기록한다."""


def applies_to_japanese_context(payload: dict[str, Any] | None) -> bool:
    payload = payload or {}
    country = str(payload.get("setting_country") or payload.get("country") or "").strip().lower()
    category = " ".join(str(payload.get(key) or "") for key in (
        "category", "category_name", "category_name_ko", "category_name_en"
    )).lower()
    return country in {"일본", "japan", "jp"} or "日本昔話" in category or "japanese folktale" in category


def japanese_period_guideline(*, force_refresh: bool = False) -> str:
    """Read the active guideline from Supabase global_settings with short caching."""
    global _cached_value, _cached_at
    now = time.monotonic()
    with _lock:
        if not force_refresh and _cached_value and now - _cached_at < _CACHE_SECONDS:
            return _cached_value
        try:
            from services.web_admin_client import web_admin_client

            response = web_admin_client.supabase_get(
                "global_settings",
                params={"select": "value", "key": f"eq.{GUIDELINE_KEY}"},
                timeout=8,
            )
            rows = response.json() if response is not None and response.status_code == 200 else []
            value = str(rows[0].get("value") or "").strip() if rows else ""
            _cached_value = value or _SAFE_FALLBACK
            _cached_at = now
            if not value:
                print(f"[JapanesePeriodGuideline] DB setting missing; using safe fallback ({GUIDELINE_KEY})")
        except Exception as exc:
            _cached_value = _SAFE_FALLBACK
            _cached_at = now
            print(f"[JapanesePeriodGuideline] DB read failed; using safe fallback: {exc}")
        return _cached_value


def reset_guideline_cache() -> None:
    """Clear cache for tests and operator-triggered refreshes."""
    global _cached_value, _cached_at
    with _lock:
        _cached_value = ""
        _cached_at = 0.0
