"""Shared character census and immutable visual-design contract."""
from __future__ import annotations

LEGACY_REFERENCE_HAIR_LOCK = (
    "Use the exact existing approved reference portrait for the hairline, shaved-scalp area and boundary, "
    "hair length, and topknot/braid shape, size, position and direction. Do not infer, redesign or replace "
    "any hair feature that is not documented; preserve the visible reference hairstyle unchanged."
)


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def approved_reference(character):
    return bool(character.get("image_url") or character.get("reference_fingerprint")
                or character.get("design_approved") is True)


def _characters(context):
    anchors = context.get("character_anchors") or context
    return [item for item in [anchors.get("main_character"),
            *(anchors.get("supporting_characters") or [])] if isinstance(item, dict)]


def select_reference_characters(context):
    """Keep the lead, every recurring person, and approved existing designs.

    Older, already prepared character packages have no census. Preserve those
    entries instead of silently discarding their established reference assets.
    New identity-stage responses always pass the strict census validator first.
    """
    characters = _characters(context)
    return [character for index, character in enumerate(characters)
            if index == 0 or approved_reference(character)
            or "scene_numbers" not in character
            or len(set(character.get("scene_numbers") or [])) >= 2]


def validate_character_identity(identity, scenes, existing=None):
    if not isinstance(identity, dict):
        raise ValueError("Character identity must be an object")
    known = {int(scene.get("scene_number") or scene.get("scene_order") or index)
             for index, scene in enumerate(scenes, 1)}
    census = identity.get("scene_cast")
    if not isinstance(census, list):
        raise ValueError("Character identity needs the complete scene_cast census")
    seen, appearances, normalized_cast = set(), {}, []
    for entry in census:
        if not isinstance(entry, dict) or type(entry.get("scene_number")) is not int:
            raise ValueError("Character census requires integer scene_number values")
        number = entry["scene_number"]
        names = entry.get("characters")
        if number not in known or number in seen or not isinstance(names, list):
            raise ValueError("Character census contains duplicate or unknown scenes")
        if any(not _text(name) for name in names):
            raise ValueError("Character census names must be nonempty strings")
        seen.add(number)
        names = list(dict.fromkeys(_text(name) for name in names))
        normalized_cast.append({"scene_number": number, "characters": names})
        for name in names:
            appearances.setdefault(name, set()).add(number)
    if seen != known:
        raise ValueError("Character census must cover every final scene exactly once")
    if not isinstance(identity.get("main_character"), dict):
        raise ValueError("Main character definition is missing")
    supporting = identity.get("supporting_characters")
    if not isinstance(supporting, list) or any(not isinstance(item, dict) for item in supporting):
        raise ValueError("Supporting characters must be an array of character definitions")
    prior = {_text(item.get("name")): item for item in _characters(existing or {})
             if approved_reference(item)}
    characters, names = [], set()
    for source in [identity["main_character"], *supporting]:
        name = _text(source.get("name"))
        if not name or name in names:
            raise ValueError("Character definitions need unique canonical names")
        names.add(name)
        character = dict(source)
        previous = prior.get(name)
        if previous:
            # A new census may update appearances, never replace an approved face.
            character.update({key: value for key, value in previous.items()
                              if key not in ("scene_numbers", "aliases")})
            if not _text(previous.get("hair_design_en")):
                character["hair_design_en"] = LEGACY_REFERENCE_HAIR_LOCK
        for field in ("visual_dna_en", "wardrobe_en", "hair_design_en", "continuity_instruction"):
            if not _text(character.get(field)):
                raise ValueError(f"Character {name} is missing {field}")
        raw_numbers = source.get("scene_numbers")
        if not isinstance(raw_numbers, list) or any(type(number) is not int for number in raw_numbers):
            raise ValueError(f"Character {name} needs integer scene_numbers")
        actual = appearances.get(name, set())
        if set(raw_numbers) != actual:
            raise ValueError(f"Character {name} scene_numbers disagree with the visual census")
        aliases = character.get("aliases") or []
        if not isinstance(aliases, list) or any(not _text(alias) for alias in aliases):
            raise ValueError(f"Character {name} aliases must be names or stable role labels")
        character.update(name=name, scene_numbers=sorted(actual),
                         aliases=list(dict.fromkeys(_text(alias) for alias in aliases)))
        characters.append(character)
    missing = sorted(name for name, numbers in appearances.items() if len(numbers) >= 2 and name not in names)
    if missing:
        raise ValueError("Missing recurring character designs: " + ", ".join(missing))
    for name, character in prior.items():
        if name not in names:
            characters.append({**character, "scene_numbers": sorted(appearances.get(name, set())),
                               "hair_design_en": _text(character.get("hair_design_en")) or LEGACY_REFERENCE_HAIR_LOCK})
    normalized = {**identity, "main_character": characters[0], "supporting_characters": characters[1:],
                  "scene_cast": sorted(normalized_cast, key=lambda item: item["scene_number"]),
                  "reference_policy": "main_and_every_person_in_two_distinct_scenes"}
    selected = select_reference_characters(normalized)
    return {**normalized, "main_character": selected[0], "supporting_characters": selected[1:]}


def character_design_anchors(identity):
    characters = select_reference_characters(identity)
    ready = sum(bool(_text(character.get("image_url"))) for character in characters)
    return {**identity, "character_image_generation": {
        "enabled": True, "status": "ready" if ready == len(characters) else "pending",
        "count": ready, "required_count": len(characters),
        "stage": "after_script_before_media_prompts"}}


def character_continuity_prompt(character):
    name = _text(character.get("name")) or "character"
    parts = [f"{name}: locked visual identity: {_text(character.get('visual_dna_en'))}"]
    if _text(character.get("hair_design_en")):
        parts.append(f"Exact hair design: {character['hair_design_en']}")
    parts.extend([f"Wardrobe: {_text(character.get('wardrobe_en'))}",
                  _text(character.get("continuity_instruction")),
                  "Preserve the same hairline, shaved-scalp area, hair length, and knot/braid shape, position and direction. "
                  "Never swap another person's hairstyle or face. Only a story-explicit approved variant may change them."])
    return ". ".join(part for part in parts if part)


def scene_continuity_prompt(anchors, scene_numbers):
    numbers = set(scene_numbers)
    characters = [character for character in _characters(anchors)
                  if "scene_numbers" not in character or numbers.intersection(character.get("scene_numbers") or [])]
    if not characters:
        return ""
    return ("Locked character designs for the named people ONLY in their applicable scenes; do not add absent people: "
            + " | ".join(("Applicable scenes: " + ", ".join(str(number) for number in sorted(
                numbers.intersection(character.get("scene_numbers") or []))) + ". "
                if "scene_numbers" in character else "") + character_continuity_prompt(character)
                for character in characters))
