"""Category-aware character diversity contract shared by every content type."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

VERSION = "character-diversity-v1"

# Pools describe dramatic/visual functions, not fixed faces. The identity stage
# combines one pool entry with age, build, facial geometry, hair, wardrobe and a
# signature prop/gesture, so recurring categories do not converge on one cast.
CATEGORY_ARCHETYPES: dict[str, list[str]] = {
    "옛날이야기": ["떠돌이 약초꾼", "몰락한 양반가의 실무형 딸", "무뚝뚝한 대장장이", "눈치 빠른 장터 상인", "선량하지만 완고한 촌로", "말보다 행동이 빠른 포졸", "비밀을 지닌 산사 승려", "재치 있는 어린 심부름꾼"],
    "탈북사연": ["국경 장마당 생존자", "원칙적인 철도 노동자", "가족을 지키는 현실형 어머니", "말수가 적은 청년 탈출자", "적응을 돕는 상담가", "의심과 연민 사이의 보안원", "고향 기억을 간직한 노년 인물", "새 직업을 배우는 정착민"],
    "한국사연": ["지친 중년 직장인", "단정하고 냉정한 전문직 여성", "생활감 있는 자영업자", "불안을 숨긴 세련된 배우자", "보수적인 부모 세대", "자유로운 예술가형 청년", "책임감 강한 돌봄 노동자", "온화하지만 비밀이 있는 노년 인물"],
    "해외감동": ["낯선 도시의 이주 노동자", "원칙적인 현지 공무원", "다문화 가정의 보호자", "말이 통하지 않아도 돕는 상인", "편견을 깨는 학생", "재난 현장의 구조자", "은퇴한 지역 공동체 리더", "두 문화를 잇는 통역자"],
    "무협": ["흉터 있는 유랑 검객", "부채를 쓰는 책사", "장신의 창술가", "약초와 독에 밝은 의원", "몰락 문파의 후계자", "웃는 얼굴의 정보상", "과묵한 호위무사", "기이한 장신구의 은둔 고수"],
    "황혼19금": ["품위를 지키는 은퇴 전문직", "새 삶을 시작한 중년 자영업자", "솔직한 취미 모임 리더", "외로움을 숨긴 배우자", "활동적인 귀촌인", "세련된 문화센터 강사", "완고하지만 다정한 홀몸 노인", "가족 눈치를 보는 재혼 희망자"],
    "English Folktales": ["weathered village healer", "quick-witted miller's child", "stern castle steward", "wandering musician", "retired royal guard", "mysterious forest keeper", "practical market widow", "curious apprentice scholar"],
    "日本昔話": ["旅の薬売り", "芯の強い宿屋の娘", "無口な木工職人", "機転の利く行商人", "頑固で情の深い村長", "若い寺男", "秘密を抱える山伏", "好奇心旺盛な奉公人"],
    "일본사건": ["피로를 숨긴 일본 회사원", "절제된 전문직 여성", "도쿄 외곽의 자영업자", "체면을 중시하는 중년 배우자", "보수적인 지방 부모", "독립적인 프리랜서", "세심한 돌봄 종사자", "과거를 숨긴 은퇴자"],
    "판타지/sf": ["현실적인 우주선 정비사", "기억을 잃은 마도 기록관", "비인간 외교관", "낡은 외골격의 용병", "금지 기술을 연구하는 학자", "변방 행성의 밀수 조종사", "생태 도시의 치료사", "왕조의 마지막 인공 생명체"],
    "일상/웹툰": ["완벽주의 신입 사원", "무심한 동네 카페 사장", "패션이 강한 대학생", "생활력 좋은 프리랜서", "참견 많은 이웃", "과묵한 운동 코치", "엉뚱한 어린이집 교사", "깔끔하지만 허당인 공무원"],
    "지식/미스터리": ["현장형 과학 기자", "회의적인 법의학자", "낡은 자료를 모으는 사서", "관찰력이 좋은 박물관 큐레이터", "숫자에 집착하는 분석가", "괴담을 싫어하는 역사학자", "말수가 적은 탐사 사진가", "은퇴한 사건 기록관"],
    "힐링/동화": ["작은 마을의 빵집 주인", "계절을 돌보는 정원사", "길 잃은 어린 여행자", "말을 아끼는 우체부", "동물과 지내는 숲지기", "낡은 장난감을 고치는 노인", "걱정 많은 구름 요정", "별빛을 모으는 밤지기"],
}

FALLBACK_ARCHETYPES = ["practical caregiver", "reserved professional", "independent craftsperson", "observant student", "community elder", "restless traveler", "methodical investigator", "warm local merchant"]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def category_key(payload: dict[str, Any]) -> str:
    raw = _text(payload.get("category_name")) or _text(payload.get("category")) or _text(payload.get("category_name_ko"))
    folded = raw.casefold().replace("・", "/")
    aliases = {
        "fantasy/sf": "판타지/sf", "판타지·sf": "판타지/sf", "daily/webtoon": "일상/웹툰",
        "knowledge/mystery": "지식/미스터리", "healing/fairy tale": "힐링/동화",
        "japanese domestic drama": "일본사건", "일본사연": "일본사건",
    }
    return aliases.get(folded, raw or "general")


def archetype_pool(payload: dict[str, Any]) -> list[str]:
    key = category_key(payload)
    matched = next((value for name, value in CATEGORY_ARCHETYPES.items() if name.casefold() == key.casefold()), None)
    return list(matched or FALLBACK_ARCHETYPES)


def _registry_path() -> Path:
    configured = os.getenv("AIR_CHARACTER_DIVERSITY_REGISTRY")
    return Path(configured) if configured else Path.home() / ".air-studio" / "character-diversity.json"


def _load_registry() -> dict[str, list[dict[str, str]]]:
    path = _registry_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def recent_designs(payload: dict[str, Any], limit: int = 24) -> list[dict[str, str]]:
    return list(_load_registry().get(category_key(payload), []))[-limit:]


def diversity_contract(payload: dict[str, Any]) -> str:
    recent = [] if category_key(payload) == "general" else recent_designs(payload)
    recent_text = json.dumps(recent[-12:], ensure_ascii=False) if recent else "[]"
    return (
        f"Apply {VERSION} to every retained character. Category archetype pool: "
        f"{json.dumps(archetype_pool(payload), ensure_ascii=False)}. Choose and remix fitting archetypes; never copy an entire stock design. "
        "For each character return archetype, facial_signature, silhouette_signature, prop_behavior_signature, "
        "palette (2-4 named colors), reference_sheet_prompt, and scene_variation_rules. visual_dna_en must explicitly cover "
        "age range, build, face shape, eyes/brows/nose/lips, skin/lived-in detail, exact hair, posture and gesture habit. "
        "The three signature fields must be concrete and visually observable. Assign a distinct palette per production while preserving the selected image style. "
        "reference_sheet_prompt must request the same person in front, profile, waist-up, full-body and expression views. "
        "scene_variation_rules may change only story-supported wardrobe, grooming, fatigue and expression; identity geometry remains locked. "
        "Compare against recent same-category designs below. If two or more of face, silhouette, and prop/behavior overlap, redesign before returning. "
        f"Recent designs: {recent_text}"
    )


def _signature(character: dict[str, Any]) -> dict[str, str]:
    return {key: _text(character.get(key)).casefold() for key in
            ("facial_signature", "silhouette_signature", "prop_behavior_signature")}


def _compact(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣ぁ-んァ-ン一-龯]+", "", value.casefold())


def enrich_and_validate(identity: dict[str, Any], payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    prior_names = {_text(c.get("name")) for c in [((existing or {}).get("main_character") or {}), *((existing or {}).get("supporting_characters") or [])] if isinstance(c, dict)}
    recent = [] if category_key(payload) == "general" else recent_designs(payload)
    pool = archetype_pool(payload)
    characters = [identity.get("main_character"), *(identity.get("supporting_characters") or [])]
    for index, character in enumerate(c for c in characters if isinstance(c, dict)):
        character.setdefault("archetype", pool[int(hashlib.sha256((_text(character.get('name')) + str(index)).encode()).hexdigest(), 16) % len(pool)])
        required = ("facial_signature", "silhouette_signature", "prop_behavior_signature")
        dna = _text(character.get("visual_dna_en")) or "the locked approved face and body design"
        character.setdefault("facial_signature", f"distinct facial geometry from {dna}")
        character.setdefault("silhouette_signature", f"distinct body and wardrobe silhouette from {dna}; {_text(character.get('wardrobe_en'))}")
        character.setdefault("prop_behavior_signature", _text(character.get("continuity_instruction")) or "a unique story-supported gesture habit")
        palette = character.get("palette")
        if not isinstance(palette, list) or not 2 <= len([p for p in palette if _text(p)]) <= 4:
            character["palette"] = ["charcoal", "muted blue", "warm ivory"]
        character.setdefault("reference_sheet_prompt", "Same locked person in front, profile, waist-up, full-body, and expression-sheet views; neutral light and background.")
        character.setdefault("scene_variation_rules", "Keep face, body geometry, hair and signature silhouette fixed; vary only story-supported wardrobe, grooming, fatigue and expression.")
        if _text(character.get("name")) in prior_names:
            continue
        current = _signature(character)
        for old in recent:
            overlap = sum(bool(_compact(current[k])) and _compact(current[k]) == _compact(_text(old.get(k))) for k in current)
            if overlap >= 2:
                raise ValueError(f"Character {_text(character.get('name'))} duplicates at least two recent signature slots")
    identity["character_design_system"] = {"version": VERSION, "category": category_key(payload), "archetype_pool": pool,
        "rules": ["character_dna", "recent_duplicate_check", "three_signature_slots", "production_palette", "reference_sheet", "scene_variation"]}
    return identity


def record_designs(identity: dict[str, Any], payload: dict[str, Any]) -> None:
    if category_key(payload) == "general":
        return
    path = _registry_path()
    registry = _load_registry()
    key = category_key(payload)
    entries = registry.setdefault(key, [])
    for character in [identity.get("main_character"), *(identity.get("supporting_characters") or [])]:
        if isinstance(character, dict):
            entries.append({"name": _text(character.get("name")), "archetype": _text(character.get("archetype")), **_signature(character)})
    registry[key] = entries[-80:]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
