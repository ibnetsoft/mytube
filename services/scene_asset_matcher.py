"""장면-에셋 자동 매칭 계획 수립.

[AIR-0107] 파일명 우선 매칭으로 시작했으나, 실제 제작 워크플로우
(2x2 그리드 생성 → 크롭 → 씬 카드에 수동 업로드 → 외부 툴에서 영상화 →
일괄 업로드)에서는 영상 파일명에 씬 번호가 들어갈 이유가 없다는 점이
확인되어 재설계됐다 (docs/UPLOAD_PIPELINE.md).

매칭 신뢰도 체계:
  - "scene/sc/s + 숫자" 명시 패턴  → 사용자가 의도적으로 붙인 이름. 확정(자동 반영).
  - 순수 앞자리 숫자(예: 1_final.mp4) → 외부 툴의 테이크/버전 번호일 수 있어
    힌트로만 취급. AI 대조가 같은 씬을 가리키면 확정, 아니면 리뷰 대상.
  - AI 매칭(레퍼런스 이미지 대조)     → confidence "high"만 자동 반영,
    "medium"/"low"는 needs_review로 분리해 사용자가 확인 후 반영.

needs_review 항목은 DB에 커밋되지 않는다 - 파일은 이미 디스크에 저장돼
있으므로, 프론트의 리뷰 UI에서 확인하면 /api/image/assign-scene-media 로
반영한다.
"""
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

# 명시적 씬 표기: scene_01, sc-3, s12 등. 사용자가 의도적으로 붙인 이름.
_EXPLICIT_SCENE_PATTERN = re.compile(
    r"(?:^|[^a-z0-9])(?:scene|sc|s)[\s_-]*0*(\d+)(?:[^0-9]|$)", re.IGNORECASE
)
# 순수 앞자리 숫자: 003_result.webp 등. 의도적 이름일 수도, 외부 툴의
# 테이크 번호일 수도 있어 힌트로만 쓴다.
_BARE_NUMBER_PATTERN = re.compile(r"^0*(\d+)(?:[\s_.-]|$)")

_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def extract_scene_number(filename: str) -> Optional[int]:
    """파일명에서 씬 번호 추출 (명시 패턴 우선, 없으면 앞자리 숫자)."""
    number, _ = extract_scene_hint(filename)
    return number


def extract_scene_hint(filename: str) -> Tuple[Optional[int], bool]:
    """파일명에서 (씬 번호, 명시적 여부)를 추출한다.

    명시적(explicit=True)  : scene/sc/s 키워드가 붙은 번호 - 사용자 의도가 명백.
    비명시적(explicit=False): 파일명 맨 앞의 순수 숫자 - 힌트로만 취급.
    """
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    match = _EXPLICIT_SCENE_PATTERN.search(stem)
    if match:
        value = int(match.group(1))
        return (value, True) if value > 0 else (None, False)
    match = _BARE_NUMBER_PATTERN.search(stem)
    if match:
        value = int(match.group(1))
        return (value, False) if value > 0 else (None, False)
    return None, False


def _normalize_ai_entry(entry: Any) -> Optional[Dict[str, Any]]:
    """AI 매핑 항목을 {scene, confidence} 형태로 정규화.

    구형 int 매핑({filename: 3})은 high 신뢰도로 취급해 하위 호환 유지.
    """
    if entry is None:
        return None
    if isinstance(entry, dict):
        scene = entry.get("scene")
        confidence = str(entry.get("confidence") or "medium").lower()
        if confidence not in _CONFIDENCE_ORDER:
            confidence = "medium"
    else:
        scene = entry
        confidence = "high"
    try:
        scene = int(scene)
    except (TypeError, ValueError):
        return None
    return {"scene": scene, "confidence": confidence}


def build_assignment_plan(
    assets: Iterable[Dict[str, Any]],
    valid_scene_numbers: Iterable[int],
    existing_slots: Dict[Tuple[int, str], bool],
    ai_mapping: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """업로드된 에셋들의 배정 계획을 세운다.

    반환 카테고리:
      matched      - 자동 반영해도 되는 확정 매칭
      needs_review - 추정 매칭. DB 반영 전 사용자 확인 필요
      unmatched    - 어떤 근거로도 씬을 못 찾음
      duplicates   - 이미 찬 슬롯 또는 같은 업로드 내 중복
      invalid      - 씬 번호가 범위 밖이거나 형식 오류

    슬롯 선점은 업로드 순서가 아니라 신뢰도 순서로 진행한다 - 명시적
    파일명 매칭이 AI 추측보다 항상 먼저 슬롯을 가진다.
    """
    valid_scenes: Set[int] = {int(value) for value in valid_scene_numbers}
    ai_mapping = ai_mapping or {}
    claimed_slots: Set[Tuple[int, str]] = set()
    result: Dict[str, List[Dict[str, Any]]] = {
        "matched": [],
        "needs_review": [],
        "unmatched": [],
        "duplicates": [],
        "invalid": [],
    }

    # 1) 각 에셋의 매칭 근거를 평가해 (확정/리뷰/실패) 후보로 분류
    resolved: List[Dict[str, Any]] = []
    for asset in assets:
        filename = str(asset.get("original_name") or "")
        media_type = "video" if asset.get("is_video") else "image"
        hint_scene, hint_explicit = extract_scene_hint(filename)
        ai_entry = _normalize_ai_entry(ai_mapping.get(filename))

        scene_number: Optional[int] = None
        match_source = ""
        confidence = ""
        review = False

        if hint_explicit:
            # 사용자가 의도적으로 씬 번호를 붙인 경우 - 확정
            scene_number = hint_scene
            match_source = "filename"
            confidence = "high"
            priority = 0
        elif hint_scene is not None:
            # 앞자리 숫자 힌트 - AI 대조 결과와 합치할 때만 확정
            if ai_entry and ai_entry["scene"] == hint_scene:
                scene_number = hint_scene
                match_source = "filename+ai"
                confidence = "high"
                priority = 1
            elif ai_entry:
                # 힌트와 AI가 불일치 - AI 쪽을 제안값으로 리뷰에 올림
                scene_number = ai_entry["scene"]
                match_source = "ai"
                confidence = ai_entry["confidence"]
                review = True
                priority = 9
            else:
                # AI 판단 없음 - 힌트만으로 자동 반영하지 않음 (외부 툴
                # 테이크 번호 오탐 방지). 힌트를 제안값으로 리뷰에 올림.
                scene_number = hint_scene
                match_source = "filename_hint"
                confidence = "low"
                review = True
                priority = 9
        elif ai_entry:
            scene_number = ai_entry["scene"]
            match_source = "ai"
            confidence = ai_entry["confidence"]
            if confidence == "high":
                priority = 2
            else:
                review = True
                priority = 9
        else:
            result["unmatched"].append({**asset, "reason": "no_scene_match"})
            continue

        resolved.append({
            "asset": asset,
            "filename": filename,
            "media_type": media_type,
            "scene_number": scene_number,
            "match_source": match_source,
            "confidence": confidence,
            "review": review,
            "priority": priority,
        })

    # 2) 신뢰도 순으로 정렬해 슬롯 선점 (같은 신뢰도면 업로드 순서 유지)
    resolved.sort(key=lambda item: item["priority"])

    for item in resolved:
        asset = item["asset"]
        scene_number = item["scene_number"]
        media_type = item["media_type"]
        base = {
            **asset,
            "scene_number": scene_number,
            "media_type": media_type,
            "match_source": item["match_source"],
            "confidence": item["confidence"],
        }

        if scene_number not in valid_scenes:
            result["invalid"].append({**base, "reason": "scene_out_of_range"})
            continue

        slot = (scene_number, media_type)

        if item["review"]:
            # 리뷰 항목은 슬롯을 선점하지 않는다 - 제안 씬이 이미 찼는지만
            # 표시해서 사용자가 판단할 수 있게 한다.
            result["needs_review"].append({
                **base,
                "slot_occupied": bool(existing_slots.get(slot)) or slot in claimed_slots,
            })
            continue

        if existing_slots.get(slot):
            result["duplicates"].append({**base, "reason": "scene_slot_occupied"})
            continue
        if slot in claimed_slots:
            result["duplicates"].append({**base, "reason": "duplicate_in_upload"})
            continue

        claimed_slots.add(slot)
        result["matched"].append(base)

    return result


def find_missing_scenes(scenes: Iterable[Dict[str, Any]]) -> Dict[str, List[int]]:
    missing_images: List[int] = []
    missing_videos: List[int] = []

    for scene in scenes:
        number = int(scene["scene_number"])
        if not scene.get("image_url"):
            missing_images.append(number)
        if not scene.get("video_url"):
            missing_videos.append(number)

    return {"images": missing_images, "videos": missing_videos}
