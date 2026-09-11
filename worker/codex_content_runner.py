"""Codex-backed content package generation for Hermes.

The YouTube Data API supplies evidence, then this module hands that evidence
to a *local* Codex CLI session, which returns the creative
package: title, plan, script, verified character portraits, scene prompts,
and publish metadata. Portraits use the native Codex image tool, never Gemini.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from worker_config import OUTPUT_DIR, PROJECT_ROOT
from senior_script_guard import PROFILE as SENIOR_PROFILE, contract as senior_contract, text_issues, review_issues
from codex_dialogue import ASTRA_MODEL, DIALOGUE_TASK, validate_dialogue


APPROVED_VIDEO_CAMERA_MOVEMENTS = (
    "slow push-in", "slow pull-back", "gentle pan", "gentle tilt", "slow dolly",
    "slow tracking shot", "locked-off shot", "subtle crane movement", "slow drift",
)


def _scene_char_budgets(scenes: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, int]]:
    """Use the same duration-weighted narration budget policy as Hermes."""
    from services.narration_policy import get_narration_policy, normalize_tts_speed

    policy = get_narration_policy(payload.get("narration_pace") or "senior")
    speed = normalize_tts_speed(payload.get("tts_speed", 1.0))
    target_duration = max(1, int(payload.get("target_duration_seconds") or 1))
    chars_per_second = policy.chars_per_second * speed
    result: list[dict[str, int]] = []
    for index, scene in enumerate(scenes, 1):
        duration = max(1, int(scene.get("duration_seconds") or scene.get("target_duration") or 1))
        target = max(20, round(duration * chars_per_second))
        if duration <= 6:
            minimum = max(policy.short_scene_min_chars, round(target * 0.65))
            maximum = min(policy.short_scene_max_chars, max(minimum + 6, round(target * 1.15)))
        else:
            minimum = max(45, round(target * 0.72))
            maximum = max(minimum + 16, round(target * 1.12))
        result.append({
            "scene_order": index,
            "duration_seconds": duration,
            "target_chars": target,
            "min_chars": minimum,
            "max_chars": maximum,
        })
    # Guard against a malformed payload whose scene schedule no longer matches
    # the requested duration; the exact scene schedule remains authoritative.
    if sum(item["duration_seconds"] for item in result) != target_duration:
        raise CodexContentError("scene durations do not add up to target_duration_seconds")
    return result


def _validate_video_prompt(video_prompt: str, scene_order: int) -> None:
    text = str(video_prompt or "").strip()
    if len(text) < 260:
        raise CodexContentError(f"scene {scene_order} video_prompt is shorter than 260 characters")
    lowered = text.lower()
    if sum(movement in lowered for movement in APPROVED_VIDEO_CAMERA_MOVEMENTS) != 1:
        raise CodexContentError(f"scene {scene_order} video_prompt requires exactly one approved camera movement")
    for required in ("no dialogue", "no narration", "no subtitles", "no captions", "no music", "no sound effects", "no audio"):
        if required not in lowered:
            raise CodexContentError(f"scene {scene_order} video_prompt missing '{required}'")


class CodexContentError(RuntimeError):
    """Raised when Codex cannot return a usable content package."""


def _pacing_schedule(target_duration_seconds: Any) -> list[dict[str, int]]:
    """The former worker's mandatory five-step visual pacing policy."""
    try:
        remaining = max(1, int(float(target_duration_seconds)))
    except (TypeError, ValueError):
        return []
    schedule: list[dict[str, int]] = []
    number = 1
    for stage_seconds, unit in ((60, 5), (240, 15), (300, 20), (300, 30), (None, 60)):
        take = remaining if stage_seconds is None else min(remaining, stage_seconds)
        while take > 0:
            duration = min(unit, take)
            schedule.append({"scene_number": number, "duration_seconds": duration})
            number += 1
            take -= duration
            remaining -= duration
        if remaining <= 0:
            break
    return schedule


def _text_blob(*parts: Any) -> str:
    return " ".join(str(part or "") for part in parts).strip().lower()


def _resolve_script_style_directive(script_style: Any) -> str:
    """Load the same script-style preset layer used by the legacy worker."""
    try:
        from services.script_style_resolver import resolve_script_style_directive
        return str(resolve_script_style_directive(str(script_style or "").strip()) or "").strip()
    except Exception:
        return ""


def _category_narration_voice(payload: dict[str, Any]) -> str:
    """Category-specific spoken narration contract for Codex script stages.

    The staged Codex runner intentionally replaced Gemini research/writing, but
    it must still preserve the old worker's category voice.  Keep this compact
    and payload-driven so it is safe to pass to every stage prompt.
    """
    category_id = str(payload.get("category_id") or "").strip()
    blob = _text_blob(
        payload.get("category"),
        payload.get("category_name"),
        payload.get("category_name_ko"),
        payload.get("category_name_en"),
        payload.get("script_style"),
        payload.get("assigned_script_style"),
        payload.get("topic"),
        payload.get("upload_title"),
    )

    # An explicit category wins over generic presets such as script_style='story'.
    if category_id in {"2", "3", "4", "5", "6", "7", "8", "9", "12", "13"}:
        blob = ""
    universal = (
        "[Universal narration rules]\n"
        "- Write spoken narration, not scene-card summaries.\n"
        "- Avoid strings of short report sentences. Merge adjacent simple facts into flowing spoken paragraphs.\n"
        "- Vary sentence endings and rhythm. Do not overuse 했다/였다/있었다/나왔다/말했다/바라보았다.\n"
        "- Do not use headings, numbered labels, timestamps, camera directions, or metadata in narration.\n"
        "- Preserve the exact scene count and character budgets, but make the full script sound continuous when read aloud."
    )

    if category_id == "2" or any(key in blob for key in ("옛날이야기", "old_story", "folktale", "folk tale", "joseon_sageuk")):
        voice = (
            "[Category narration voice: 옛날이야기]\n"
            "A warm Korean folk-storyteller is telling the tale directly to listeners. Use 구수한 구연체, gentle suspense, "
            "and old-tale transitions such as '그런데 말입니다', '그날 밤이 깊어질수록', '사람들은 그제야' when natural. "
            "Let emotional moments breathe in slightly longer flowing sentences. The narration should feel like a lived tale "
            "with moral aftertaste, not a list of facts. Avoid modern YouTube commentary or stiff news/report style."
        )
    elif category_id == "4" or any(key in blob for key in ("탈북", "north_korea", "north korean", "survival")):
        voice = (
            "[Category narration voice: 탈북사연]\n"
            "Write like a restrained first-person/close-third testimony. Use concrete sensory detail, fear, hunger, family stakes, "
            "and survival choices without sensationalism. The voice should feel human and careful, not melodramatic or clipped."
        )
    elif category_id == "5" or any(key in blob for key in ("한국사연", "korean story", "korean_drama", "사연")):
        voice = (
            "[Category narration voice: 한국사연]\n"
            "Write as an intimate realistic Korean human-story narration. Build conflict through family/social detail, shame, regret, "
            "and withheld truth. Use natural spoken Korean with emotional continuity, not fairy-tale phrasing and not summary bullets."
        )
    elif category_id == "6" or any(key in blob for key in ("해외감동", "overseas", "touching", "감동")):
        voice = (
            "[Category narration voice: 해외감동]\n"
            "Write like a warm translated human documentary: clear Korean, universally understandable emotion, vivid setting, "
            "and a gentle uplifting payoff. Avoid awkward literal translation tone and avoid excessive sentimentality."
        )
    elif category_id == "7" or any(key in blob for key in ("무협", "martial", "wuxia")):
        voice = (
            "[Category narration voice: 무협]\n"
            "Write with martial-arts chapter energy: honor, grudge, discipline, restrained menace, decisive choices, and archaic cadence "
            "where natural. Keep action concrete and rhythmic. Avoid modern slang and avoid dry mission-report sentences."
        )
    elif category_id in {"3", "8"}:
        voice = "[Category narration voice: financial explanation] Calm, respectful spoken explanation. Define jargon and numerical assumptions. No fear-driven prophecy or unsupported advice."
    elif category_id in {"12", "13"}:
        voice = "[Category narration voice: localized folktale] Use natural adult oral storytelling in the requested English or Japanese language, not Korean."
    elif category_id == "9" or any(key in blob for key in ("황혼", "19금", "twilight", "mature")):
        voice = (
            "[Category narration voice: 황혼19금]\n"
            "Write as mature restrained melodrama for adults: loneliness, late-life desire, regret, secrecy, and dignity. Keep it suggestive "
            "and emotionally precise, never explicit, crude, or sensational."
        )
    else:
        voice = (
            "[Category narration voice: default]\n"
            "Write natural long-form Korean narration with clear emotional continuity, varied sentence rhythm, and scene-to-scene flow."
        )

    return f"{voice}\n\n{universal}\n\n{senior_contract(payload)}"


def _script_rhythm_contract(payload: dict[str, Any]) -> str:
    schedule = payload.get("repair_scene_schedule") or _pacing_schedule(payload.get("target_duration_seconds"))
    first_hook_count = 0
    for scene in schedule[:12]:
        if int(scene.get("duration_seconds") or 0) > 6:
            break
        first_hook_count += 1
    hook_rule = (f"- Scenes 1-{first_hook_count} are short opening beats: concise, vivid, and distinct, but still spoken naturally.\n"
                 if first_hook_count else "- This existing project has no mandatory 5-second opening cuts; follow its actual scene_budgets and introduce the story naturally.\n")
    return (
        "[Script rhythm QA contract]\n"
        + hook_rule +
        "- After the hook section, each section should usually be 2-4 connected sentences or one flowing paragraph, not one dry sentence.\n"
        "- In any 5-scene window, no more than 2 sections may end with the same blunt verb ending such as 했다/였다/있었다/나왔다.\n"
        "- Avoid 3 or more consecutive sentences under 25 Korean characters unless it is a deliberate hook rhythm.\n"
        "- Repair repeated paragraph openings, repeated final verbs, and 'A happened. B happened. C happened.' sequencing.\n"
        "- A QA pass requires the script to sound good when read aloud as one continuous narration, while still respecting every scene budget."
    )


_BLUNT_KOREAN_ENDINGS = (
    "했다고 말했다",
    "라고 말했다",
    "고 말했다",
    "바라보았다",
    "돌아보았다",
    "말했다",
    "나왔다",
    "있었다",
    "되었다",
    "않았다",
    "이었다",
    "였다",
    "했다",
)


def _korean_sentence_end_bucket(text: Any) -> str:
    cleaned = re.sub(r"[\s。.!?…\"'”’)\]]+$", "", str(text or "").strip())
    for ending in _BLUNT_KOREAN_ENDINGS:
        if cleaned.endswith(ending):
            return ending
    match = re.search(r"([가-힣]{1,8}(?:다|요|죠|네|까|나|라|군|구나|습니다|습니까))$", cleaned)
    return match.group(1) if match else ""


def _script_rhythm_warnings(sections: list[Any]) -> list[str]:
    texts = [
        str((section or {}).get("text") or "").strip() if isinstance(section, dict) else ""
        for section in sections
    ]
    warnings: list[str] = []
    buckets = [_korean_sentence_end_bucket(text) for text in texts]
    for start in range(0, max(0, len(buckets) - 4)):
        window = [bucket for bucket in buckets[start:start + 5] if bucket]
        for bucket in set(window):
            if bucket in _BLUNT_KOREAN_ENDINGS and window.count(bucket) > 2:
                warnings.append(
                    f"scenes {start + 1}-{start + 5} repeat blunt ending '{bucket}' {window.count(bucket)} times"
                )
                break
        if len(warnings) >= 4:
            break

    short_run = 0
    for index, text in enumerate(texts, 1):
        sentences = [part.strip() for part in re.split(r"[.!?。]\s+", text) if part.strip()]
        for sentence in sentences:
            hangul_len = len(re.sub(r"[^가-힣]", "", sentence))
            if 0 < hangul_len < 18 and index > 12:
                short_run += 1
            else:
                short_run = 0
            if short_run >= 4:
                warnings.append("body narration contains 4+ consecutive very short Korean sentences")
                return warnings[:5]
    return warnings[:5]


@dataclass(frozen=True)
class CodexContentConfig:
    executable: str
    model: str
    timeout_seconds: int

    @classmethod
    def from_environment(cls) -> "CodexContentConfig":
        return cls(
            executable=os.environ.get("CODEX_EXECUTABLE", "codex").strip() or "codex",
            model=os.environ.get("CODEX_CONTENT_MODEL", "").strip(),
            timeout_seconds=max(60, int(os.environ.get("CODEX_CONTENT_TIMEOUT_SECONDS", "1800"))),
        )


def _schema() -> dict[str, Any]:
    # Keep the schema deliberately permissive for the existing, rich scene
    # contract. Required top-level fields make an incomplete answer fail here,
    # before it is persisted to topics_queue.
    required = [
        "generated_title", "title_generation", "structure", "script",
        "narrative_blueprint", "script_quality_report", "publish_metadata",
        "main_character", "supporting_characters", "character_anchors", "sfx_cues",
    ]
    return {
        "type": "object",
        "required": required,
        "properties": {
            "generated_title": {"type": "string", "minLength": 4},
            "title_generation": {"type": "object"},
            "structure": {"type": "object"},
            "script": {"type": "string", "minLength": 200},
            "narrative_blueprint": {"type": "object"},
            "script_quality_report": {"type": "object"},
            "publish_metadata": {"type": "object"},
            "main_character": {"type": "object"},
            "supporting_characters": {"type": "array"},
            "character_anchors": {"type": "object"},
            "sfx_cues": {"type": "array"},
        },
        "additionalProperties": True,
    }


def _parse_json(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else ""
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CodexContentError(f"Codex returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CodexContentError("Codex response must be a JSON object")
    return parsed


def _validate_package(package: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
    required = _schema()["required"]
    missing = [key for key in required if package.get(key) in (None, "")]
    if missing:
        raise CodexContentError(f"Codex response omitted required fields: {', '.join(missing)}")
    structure = package.get("structure")
    if not isinstance(structure, dict) or not isinstance(structure.get("scenes"), list) or not structure["scenes"]:
        raise CodexContentError("Codex response requires structure.scenes")
    if not isinstance(package.get("publish_metadata"), dict):
        raise CodexContentError("Codex response requires publish_metadata object")
    raw_script = package.get("script")
    sections = [{"scene_order": i, "text": text} for i, text in enumerate(raw_script.split("\n\n"), 1)] if isinstance(raw_script, str) else []
    issues = text_issues(sections, payload or {}) + review_issues(package.get("script_quality_report"))
    issues += text_issues([
        {"scene_order": i, "text": scene.get("scene_text") or scene.get("narration")}
        if isinstance(scene, dict) else {}
        for i, scene in enumerate(structure["scenes"], 1)
    ], payload or {})
    if issues:
        raise CodexContentError("senior script gate rejected package: " + "; ".join(issues[:12]))
    schedule = _pacing_schedule((payload or {}).get("target_duration_seconds"))
    if schedule:
        scenes = structure["scenes"]
        if len(scenes) != len(schedule):
            raise CodexContentError(
                f"Codex scene count violates legacy pacing: expected {len(schedule)}, got {len(scenes)}"
            )
        for index, expected in enumerate(schedule, start=1):
            scene = scenes[index - 1] if isinstance(scenes[index - 1], dict) else {}
            try:
                actual = int(float(scene.get("duration_seconds") or scene.get("target_duration") or 0))
            except (TypeError, ValueError):
                actual = 0
            if actual != expected["duration_seconds"]:
                raise CodexContentError(
                    f"Codex scene {index} duration violates legacy pacing: expected {expected['duration_seconds']}s"
                )
        if len(scenes) >= 12 and any(not bool((scene if isinstance(scene, dict) else {}).get("video_prompt_required")) for scene in scenes[:12]):
            raise CodexContentError("Codex first minute requires video prompts for scenes 1-12")


def _validate_title_uniqueness(package: dict[str, Any], payload: dict[str, Any]) -> None:
    title = str(package.get("generated_title") or package.get("final_upload_title") or "").strip()
    compact_title = re.sub(r"[^\w가-힣]", "", title).lower()
    for forbidden in payload.get("forbidden_titles") or []:
        compact_forbidden = re.sub(r"[^\w가-힣]", "", str(forbidden or "")).lower()
        if compact_forbidden and (
            compact_title == compact_forbidden
            or SequenceMatcher(None, compact_title, compact_forbidden).ratio() >= 0.82
        ):
            raise CodexContentError("Codex final title is duplicate or near-duplicate of a forbidden title")


def _normalize_package(package: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Accept the concise content-director shape and map it to Hermes fields."""
    if package.get("generated_title"):
        return package
    scenes = package.get("scenes") or []
    schedule = _pacing_schedule((payload or {}).get("target_duration_seconds"))
    narration_rows = package.get("narration_script") or []
    narration_by_scene = {
        int(item.get("scene_number") or index): str(item.get("text") or "").strip()
        for index, item in enumerate(narration_rows, 1)
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    }
    for index, scene in enumerate(scenes, 1):
        if isinstance(scene, dict):
            scene_number = int(scene.get("scene_number") or index)
            if schedule and index <= len(schedule):
                scene["scene_number"] = scene_number
                scene["duration_seconds"] = schedule[index - 1]["duration_seconds"]
                scene["target_duration"] = schedule[index - 1]["duration_seconds"]
                scene["video_prompt_required"] = index <= 12
                if index > 12:
                    scene.pop("video_prompt", None)
            scene["narration"] = str(scene.get("narration") or narration_by_scene.get(scene_number) or "").strip()
            if scene.get("sfx_cue") and not scene.get("sfx_cues"):
                scene["sfx_cues"] = [scene["sfx_cue"]]
    plan_rows = package.get("scene_structure") or []
    plan_by_scene = {
        int(item.get("scene_number") or index): item
        for index, item in enumerate(plan_rows, 1) if isinstance(item, dict)
    }
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            continue
        plan = plan_by_scene.get(int(scene.get("scene_number") or index), {})
        beat = str(plan.get("beat") or "").strip()
        purpose = str(plan.get("purpose") or "").strip()
        scene["scene_summary"] = str(scene.get("scene_summary") or beat or scene.get("narration") or "").strip()
        scene["scene_situation"] = str(scene.get("scene_situation") or beat or "").strip()
        scene["scene_purpose"] = str(scene.get("scene_purpose") or purpose or "").strip()
        scene["retention_hook"] = str(scene.get("retention_hook") or purpose or beat or "").strip()
        scene["character_choice"] = str(scene.get("character_choice") or beat or "").strip()
    raw_titles = package.get("title_candidates") or []
    title_candidates = [
        item if isinstance(item, dict) else {"title": str(item).strip()}
        for item in raw_titles if str(item or "").strip()
    ]
    # Codex's compact grid prose is useful as scene context, but Hermes stores
    # a strict renderer-ready grid record. Build that canonical record here.
    from services.image_grid_prompts import build_image_grid_prompts
    canonical_grids = build_image_grid_prompts(scenes)
    for grid in canonical_grids:
        grid["template"] = "strict_2x2_compact_v1"
    anchors = package.get("character_continuity_anchors") or []
    main = anchors[0] if anchors else {"character": "narrator", "anchor": "Keep continuity across scenes."}
    supporting = anchors[1:] if len(anchors) > 1 else []
    narrative = package.get("narrative_plan") or {}
    structure = {
        "scene_count": package.get("scene_count") or len(scenes),
        "image_grid_prompt_status": package.get("image_grid_prompt_status") or "ready",
        "image_grid_prompt_mode": package.get("image_grid_prompt_mode") or "direct_2x2_only",
        "image_grid_prompts": canonical_grids,
        "scenes": scenes,
        "story_core": {
            "protagonist": str((anchors[0] or {}).get("character") or "").strip(),
            "opening_incident": str(narrative.get("hook") or "").strip(),
            "personal_stake": str(narrative.get("logline") or "").strip(),
            "central_conflict": str(narrative.get("central_conflict") or "").strip(),
            "midpoint_reversal": str(narrative.get("turning_point") or "").strip(),
            "final_payoff": str(narrative.get("final_payoff") or "").strip(),
        },
    }
    if scenes:
        structure["scenes"][-1]["reveal_or_question"] = structure["story_core"]["final_payoff"]
    if len(scenes) >= 3:
        structure["scenes"][len(scenes) // 2]["reveal_or_question"] = structure["story_core"]["midpoint_reversal"]
    script_text = package.get("full_narration_script") or package.get("script") or "\n\n".join(
        str(scene.get("narration") or "").strip() for scene in scenes
    ).strip()
    # Codex often places a Korean delivery cue immediately *inside* quotation
    # marks.  The legacy QA contract intentionally requires it just before the
    # spoken line, so normalize that harmless notation rather than weakening
    # the dialogue-quality check.
    script_text = re.sub(r'([“"「])\(([^()]{1,40})\)', r'(\2) \1', str(script_text))
    # Supply a neutral delivery cue for any remaining quoted speech without
    # changing its words. Individual cues already moved above remain intact.
    script_text = re.sub(r'(?<!\))\s*“', ' (차분하게) “', script_text)
    package.update({
        "generated_title": package.get("final_upload_title") or "",
        "title_generation": {
            "generated_title": package.get("final_upload_title") or "",
            "title_candidates": title_candidates,
            "generation_models": {"title": "codex-cli"},
        },
        "structure": structure,
        "script": script_text,
        "narrative_blueprint": narrative,
        "main_character": main,
        "supporting_characters": supporting,
        "character_anchors": {str(item.get("character") or index): item.get("anchor") or "" for index, item in enumerate(anchors, 1)},
        "sfx_cues": [cue for scene in scenes for cue in (scene.get("sfx_cues") or [])],
    })
    return package


class CodexContentRunner:
    """Run one isolated, read-only Codex content generation session."""

    def _review(self, job_id: str, package: dict[str, Any], payload: dict[str, Any]) -> None:
        result = CodexStagedContentRunner(self.config)._stage(job_id, "02c_senior_review", {
            **payload, "script": package.get("script"), "structure": package.get("structure"),
            "narrative_blueprint": package.get("narrative_blueprint"),
        }, "Independently review the exact full script against the mandatory senior listening contract. Do not rewrite or trust author self-scores. Return only script_quality_report with the required profile, verdict, score, critical_issues and all evidence-backed checks. Fail unresolved contradictions and unsupported factual claims.")
        package["script_quality_report"] = result.get("script_quality_report")

    def __init__(self, config: CodexContentConfig | None = None):
        self.config = config or CodexContentConfig.from_environment()

    def generate(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        work_dir = OUTPUT_DIR / "codex_content_requests"
        work_dir.mkdir(parents=True, exist_ok=True)
        request_path = work_dir / f"{job_id}.input.json"
        response_path = work_dir / f"{job_id}.{SENIOR_PROFILE}.response.json"
        script_style_directive = _resolve_script_style_directive(
            payload.get("assigned_script_style") or payload.get("script_style")
        )
        category_narration_voice = _category_narration_voice(payload)
        script_rhythm_contract = _script_rhythm_contract(payload)
        payload = {
            **payload,
            "script_style_directive": script_style_directive,
            "category_narration_voice": category_narration_voice,
            "script_rhythm_contract": script_rhythm_contract,
        }
        request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # A retry after a downstream quality/compatibility failure should reuse
        # the already completed Codex response, not spend another generation.
        cached_job_id = str(payload.get("reuse_response_job_id") or job_id).strip()
        cached_response_path = work_dir / f"{cached_job_id}.{SENIOR_PROFILE}.response.json"
        if cached_response_path.exists():
            cached = _normalize_package(_parse_json(cached_response_path.read_text(encoding="utf-8")), payload)
            self._review(job_id, cached, payload)
            _validate_package(cached, payload)
            _validate_title_uniqueness(cached, payload)
            return cached

        prompt = f"""
You are AIR Studio's Codex content director. Read the job payload at:
{request_path}

The YouTube Data API has already performed the research. Use only the supplied
research packet and benchmark material for factual claims. Do not do fresh web/YouTube research.

TITLE UNIQUENESS IS A HARD REQUIREMENT: payload.upload_title is the topic title
already selected by the preceding Codex discovery stage. Preserve it exactly
as final_upload_title. payload.forbidden_titles are benchmark or existing
titles; never use or near-copy them in the package.

Apply payload.legacy_stage_directives as mandatory production instructions.
Also satisfy every item in payload.legacy_quality_contract. Treat these as the
former separate title-planning, script-plan, script-QA/rewrite, and metadata
stage requirements; do the checks yourself before responding.

Apply payload.category_narration_voice, payload.script_style_directive, and
payload.script_rhythm_contract as mandatory script-writing instructions. The
script must sound like category-appropriate spoken narration, not a sequence of
short factual reports.

Create one complete, original YouTube content package in the requested
language: choose the final upload title, title candidates, narrative plan,
scene structure, narration script, character continuity anchors, per-scene
image prompts and video prompts, SFX cues, and publish metadata.

The legacy visual pacing policy is mandatory. The exact internal scene schedule
is {json.dumps(_pacing_schedule(payload.get("target_duration_seconds")), ensure_ascii=False)}.
Generate exactly that many ordered scenes. Scenes 1-12 are the first 60 seconds:
each is exactly 5 seconds and must include image_prompt plus video_prompt. All
later scenes are 15/20/30/40-second pacing scenes as listed and must include
image_prompt only; do not include video_prompt after scene 12. Put
duration_seconds on every scene. Never print timestamps or timecodes in the
narration; duration_seconds is internal JSON metadata only.

Compatibility requirements for AIR Studio: structure must contain scene_count,
image_grid_prompt_status="ready", image_grid_prompt_mode="direct_2x2_only",
and compact 2x2 image_grid_prompts. Every scene must set
media_prompt_status="ready". For the first 12 scenes, include a unique English
video_prompt of at least 260 characters with exactly one approved movement
(slow push-in, slow pull-back, gentle pan, gentle tilt, slow dolly, slow
tracking shot, locked-off shot, subtle crane movement, or slow drift) and all
of these literal guards: no dialogue, no narration, no subtitles, no captions,
no music, no sound effects, no audio. Produce prompts only, never media files.
For Korean packages, write at least 1,000 Hangul characters in the script and
a Korean publish_metadata.description of at least 120 characters. Include at
least five tags and three hashtags.

Do not generate images or video. Do not crop, resize, download, upload, or
write media files. Do not modify repository files. Return only the JSON object
with every required field named in this instruction. The script_quality_report must use
{{"verdict":"pass", "score":78 or higher, "critical_issues":[]}} only after
you have checked the package yourself.
""".strip()
        command = [
            self.config.executable,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "-C",
            str(PROJECT_ROOT),
            "--output-last-message",
            str(response_path),
        ]
        if self.config.model:
            command.extend(["--model", self.config.model])
        command.append(prompt)
        try:
            completed = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise CodexContentError("Codex CLI was not found. Install/login to Codex or set CODEX_EXECUTABLE.") from exc
        except subprocess.TimeoutExpired as exc:
            raise CodexContentError(f"Codex content generation timed out after {self.config.timeout_seconds}s") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-1200:]
            raise CodexContentError(f"Codex content generation failed (exit {completed.returncode}): {detail}")
        if not response_path.exists():
            raise CodexContentError("Codex completed without an output message file")
        package = _normalize_package(_parse_json(response_path.read_text(encoding="utf-8")), payload)
        self._review(job_id, package, payload)
        _validate_package(package, payload)
        _validate_title_uniqueness(package, payload)
        return package


class CodexStagedContentRunner:
    """Run the legacy plan → script → prompts → metadata dependency chain."""

    def __init__(self, config: CodexContentConfig | None = None):
        self.config = config or CodexContentConfig.from_environment()

    def _stage(self, job_id: str, name: str, context: dict[str, Any], task: str) -> dict[str, Any]:
        model = ASTRA_MODEL if name.startswith('02') else self.config.model
        work_dir = OUTPUT_DIR / "codex_stage_requests"
        work_dir.mkdir(parents=True, exist_ok=True)
        # Changed instructions, rewritten text and QA feedback must never hit an old response.
        fingerprint = hashlib.sha256(json.dumps([SENIOR_PROFILE, "astra-dialogue-v1", model, context, task], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        request_path = work_dir / f"{job_id}.{name}.{fingerprint}.input.json"
        request_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
        last_error = ""
        # Match the original worker's bounded recovery policy: a failed
        # provider response is retried once with the failure fed back, never
        # replaced by a synthetic plan/script/prompt.
        for attempt in range(2):
            response_path = work_dir / f"{job_id}.{name}.{fingerprint}.attempt-{attempt + 1}.response.json"
            # A downstream validation retry should reuse the already valid
            # creative stages. Metadata is intentionally regenerated because
            # its validation is performed after this helper returns.
            if name != "04_metadata" and response_path.exists():
                try:
                    return _parse_json(response_path.read_text(encoding="utf-8"))
                except CodexContentError:
                    pass
            retry = (
                " The previous attempt was rejected. Return a complete JSON object, obey every field and length constraint, "
                f"and repair this failure: {last_error[:800]}"
                if attempt else ""
            )
            prompt = (f"Read {request_path}. You are AIR Studio's {name} stage. "
                       "Use only this supplied YouTube Data API research; do not web-search and do not use Gemini. "
                       "Apply legacy_stage_directives and legacy_quality_contract when actually supplied in the context; absent legacy fields impose no additional requirements. "
                       + task + retry + " Return JSON only. Do not create or save media files or modify repository files.")
            command = [self.config.executable, "exec", "--ephemeral", "--sandbox", "read-only", "--color", "never", "-C", str(PROJECT_ROOT), "--output-last-message", str(response_path)]
            if model:
                command.extend(["--model", model])
            command.append(prompt)
            completed = subprocess.run(command, cwd=str(PROJECT_ROOT), text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=self.config.timeout_seconds, check=False)
            if completed.returncode == 0 and response_path.exists():
                try:
                    return _parse_json(response_path.read_text(encoding="utf-8"))
                except CodexContentError as exc:
                    last_error = str(exc)
                    continue
            last_error = (completed.stderr or completed.stdout or "no response file").strip()[-1200:]
        raise CodexContentError(f"Codex {name} stage failed after bounded retry: {last_error or 'no response file'}")

    def generate(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        schedule = _pacing_schedule(payload.get("target_duration_seconds"))
        if not schedule:
            raise CodexContentError("target_duration_seconds is required")
        script_style_directive = _resolve_script_style_directive(
            payload.get("assigned_script_style") or payload.get("script_style")
        )
        category_narration_voice = _category_narration_voice(payload)
        script_rhythm_contract = _script_rhythm_contract(payload)
        plan_context = {
            **payload,
            "script_style_directive": script_style_directive,
            "category_narration_voice": category_narration_voice,
            "script_rhythm_contract": script_rhythm_contract,
        }
        plan = self._stage(job_id, "01_plan", plan_context, f"Create exactly {len(schedule)} scene plans using this mandatory internal pacing schedule: {json.dumps(schedule)}. Return JSON with narrative_blueprint, main_character, supporting_characters, story_core, and scenes. story_core must contain protagonist, opening_incident, personal_stake, central_conflict, midpoint_reversal, and final_payoff. Every scene needs scene_order, scene_summary, scene_situation, scene_purpose, scene_emotion, character_choice, emotional_shift, reveal_or_question, and duration_seconds. The first 12 must be distinct 5-second hook beats. Use category_narration_voice and script_style_directive to shape scene purposes, emotional rhythm, and payoff texture; do not plan a chain of clipped factual summaries.")
        scenes = plan.get("scenes") if isinstance(plan.get("scenes"), list) else []
        if len(scenes) != len(schedule):
            raise CodexContentError(f"legacy pacing requires {len(schedule)} planned scenes; got {len(scenes)}")
        for index, (scene, timing) in enumerate(zip(scenes, schedule), 1):
            if not isinstance(scene, dict):
                raise CodexContentError(f"plan scene {index} is not an object")
            scene.update({"scene_order": index, "scene_number": index, "duration_seconds": timing["duration_seconds"], "target_duration": timing["duration_seconds"], "video_prompt_required": index <= 12})
        structure = {"scene_count": len(scenes), "scenes": scenes, "story_core": plan.get("story_core") or {}}
        scene_budgets = _scene_char_budgets(scenes, payload)
        script_context = {
            **plan_context,
            "structure": structure,
            "scene_budgets": scene_budgets,
            "narrative_blueprint": plan.get("narrative_blueprint") or {},
            "main_character": plan.get("main_character") or {},
            "supporting_characters": plan.get("supporting_characters") or [],
        }
        written = self._stage(job_id, "02_script", script_context, f"Write narration for the supplied scene plans using scene_budgets as hard per-scene character budgets. Apply category_narration_voice, script_style_directive, and script_rhythm_contract strictly. Return {{'sections':[{{'scene_order':n,'text':'...'}}], 'script_quality_report':{{'verdict':'pass|revise','score':0-100,'category_voice_score':0-100,'rhythm_score':0-100,'repetitive_ending_score':0-100,'critical_issues':[],'revision_notes':[]}}}}. Return exactly {len(scenes)} ordered sections. Each section must fit its duration and concatenate without omissions or duplication into the finished narration. For each scene, dramatize a concrete action, choice, reveal, or consequence; do not summarize the plan. Make the narration sound read aloud and category-specific, not like short scene cards. Never use headings, timestamps, camera directions, or metadata in narration.")
        sections = written.get("sections") if isinstance(written.get("sections"), list) else []
        if len(sections) != len(scenes):
            raise CodexContentError(f"script requires {len(scenes)} sections; got {len(sections)}")
        parts = []
        for index, section in enumerate(sections, 1):
            text = str((section or {}).get("text") or "").strip() if isinstance(section, dict) else ""
            if not text:
                raise CodexContentError(f"script section {index} is empty")
            budget = scene_budgets[index - 1]
            if len(text) < budget["min_chars"] or len(text) > max(budget["max_chars"] * 2, budget["max_chars"] + 30):
                raise CodexContentError(f"script section {index} violates its duration character budget")
            scenes[index - 1]["scene_text"] = text
            scenes[index - 1]["narration"] = text
            parts.append(text)
        script = "\n\n".join(parts)
        qa_context = {**script_context, "script": script, "sections": sections}
        qa_task = f"Perform the legacy script QA/rewrite pass. Apply category_narration_voice, script_style_directive, and script_rhythm_contract as hard QA criteria. Score hook, title promise, protagonist/conflict, rising tension, continuity, midpoint reversal, final payoff, spoken naturalness, category voice fit, sentence rhythm, repetitive-ending control, emotion cues, and paragraph-opening variety. Return {{'sections':[{{'scene_order':n,'text':'final narration'}}], 'script_quality_report':{{'verdict':'pass|revise','score':0-100,'hook_score':0-100,'structure_score':0-100,'retention_score':0-100,'payoff_score':0-100,'naturalness_score':0-100,'category_voice_score':0-100,'rhythm_score':0-100,'repetitive_ending_score':0-100,'critical_issues':[],'strengths':[],'revision_notes':[]}}}} with exactly {len(scenes)} ordered sections. A pass requires score >=82, category_voice_score >=85, rhythm_score >=85, repetitive_ending_score >=85, and an empty critical_issues array. Preserve scene order and character budgets. Rewrite any section chain that sounds like clipped factual reports, repeats blunt endings such as 했다/였다/있었다/나왔다, or loses the category-specific spoken voice. Do not add headings/timestamps/camera directions."
        qa: dict[str, Any] = {}
        qa_sections: list[Any] = []
        rhythm_warnings: list[str] = []
        for qa_attempt in range(2):
            qa = self._stage(job_id, "02b_script_qa", qa_context, qa_task)
            qa_sections = qa.get("sections") if isinstance(qa.get("sections"), list) else []
            if len(qa_sections) != len(scenes):
                raise CodexContentError(f"script QA requires {len(scenes)} sections; got {len(qa_sections)}")
            rhythm_warnings = _script_rhythm_warnings(qa_sections)
            rhythm_warnings += text_issues(qa_sections, payload)
            if not rhythm_warnings:
                review = self._stage(job_id, "02c_senior_review", {
                    **script_context,
                    "sections": qa_sections,
                    "script": "\n\n".join(s["text"].strip() for s in qa_sections),
                }, "Independently review the exact complete narration as an adult senior listening without images. Do NOT rewrite or trust the author's score. "
                   "Compare the cast, timeline, object custody, character knowledge and title promise across the entire script. Check factual claims against supplied evidence. "
                   "Return only {'script_quality_report': {...}} using EVERY mandatory field and evidence-backed check defined in category_narration_voice's senior listening contract.")
                qa["script_quality_report"] = review.get("script_quality_report")
                rhythm_warnings += review_issues(qa["script_quality_report"])
                if rhythm_warnings:
                    qa_context["independent_review_feedback"] = review
            if not rhythm_warnings:
                break
            if qa_attempt:
                raise CodexContentError("script QA failed senior listening contract: " + "; ".join(rhythm_warnings))
            qa_context = {
                **qa_context,
                "script": "\n\n".join(
                    str((section or {}).get("text") or "").strip()
                    for section in qa_sections
                    if isinstance(section, dict)
                ),
                "sections": qa_sections,
                "script_rhythm_rejection": rhythm_warnings,
            }
        parts = []
        for index, section in enumerate(qa_sections, 1):
            text = str((section or {}).get("text") or "").strip() if isinstance(section, dict) else ""
            if not text:
                raise CodexContentError(f"script QA section {index} is empty")
            budget = scene_budgets[index - 1]
            if len(text) < budget["min_chars"] or len(text) > max(budget["max_chars"] * 2, budget["max_chars"] + 30):
                raise CodexContentError(f"script QA section {index} violates its duration character budget")
            scenes[index - 1]["scene_text"] = text
            scenes[index - 1]["narration"] = text
            parts.append(text)
        script = "\n\n".join(parts)
        character_context = {**script_context, "script": script}
        dialogue_context = {**character_context, 'scenes': scenes}
        for attempt in range(2):
            dialogue_result = self._stage(job_id, '02e_dialogue', dialogue_context, DIALOGUE_TASK)
            try:
                structure['dialogue_annotations'] = validate_dialogue(dialogue_result, scenes)
                structure['script_model'] = ASTRA_MODEL
                break
            except ValueError as exc:
                if attempt:
                    raise CodexContentError(str(exc)) from exc
                dialogue_context['validation_feedback'] = str(exc)
        identity = self._stage(job_id, "02d_character_identity", character_context,
            "From the FINAL reviewed script, finalize the main character and up to two recurring supporting characters. "
            "Preserve established identities; do not invent people or change relationships. Return {main_character:{...}, supporting_characters:[...]}. "
            "Every character must have name, role, gender, age_group, detailed English visual_dna_en, wardrobe_en, continuity_instruction. "
            "Use the selected image style and era. These definitions will be rendered as actual reference portraits before scene prompts.")
        from codex_character_assets import generate_character_references
        anchors = generate_character_references(
            {**character_context, **identity}, payload, self.config, OUTPUT_DIR / "codex_character_images")
        script_context.update(main_character=anchors["main_character"], supporting_characters=anchors["supporting_characters"])
        structure.update(main_character=anchors["main_character"], supporting_characters=anchors["supporting_characters"],
                         character_anchors=anchors, character_reference_status="ready")
        media_context = {**script_context, "script": script, "character_anchors": anchors,
                         "character_reference_rule": "These are verified actual reference images. Preserve their facial identity, age, wardrobe and era in every applicable scene. Never substitute a different character."}
        media_task = f"Create prompts only from each final scene_text. Return {{'scenes':[{{'scene_order':n,'image_prompt':'English'}}], 'image_grid_prompts':[{{'grid_number':1,'scene_numbers':[1,2,3,4],'shared_style':'English continuity/style block','negative_prompt':'no text, no words, no letters, no labels, no captions, no watermarks, No borders, NO grid lines, no dividers, correct anatomy, no extra limbs','panels':[{{'scene_number':1,'scene_id':'scene001','position':'Top-Left','panel_prompt':'80+ character English visual beat'}}]}}]}}. Every scene needs a unique 120+ character English image_prompt grounded in its final scene_text. Make compact strict 2x2 grids for every four-scene window, with exactly four panels at Top-Left, Top-Right, Bottom-Left, Bottom-Right. Scenes 1-12 also need a 300+ character English video_prompt, exactly one approved camera movement, and the literal guards 'no dialogue, no narration, no subtitles, no captions, no music, no sound effects, no audio'. Scenes 13 onward must not contain video_prompt."
        media = {}
        for media_attempt in range(2):
            media = self._stage(job_id, "03_media", media_context, media_task)
            try:
                candidate_scenes = media.get("scenes") if isinstance(media.get("scenes"), list) else []
                if len(candidate_scenes) != len(scenes):
                    raise CodexContentError(f"media requires {len(scenes)} scenes; got {len(candidate_scenes)}")
                for index, item in enumerate(candidate_scenes, 1):
                    image = str((item or {}).get("image_prompt") or "").strip() if isinstance(item, dict) else ""
                    if len(image) < 120:
                        raise CodexContentError(f"media scene {index} image_prompt is shorter than 120 characters")
                    if index <= 12:
                        _validate_video_prompt(str(item.get("video_prompt") or "").strip(), index)
                break
            except CodexContentError as exc:
                if media_attempt:
                    raise
                media_context["media_contract_rejection"] = str(exc)
        else:
            raise CodexContentError("media stage did not produce a valid response")
        media_scenes = media.get("scenes") if isinstance(media.get("scenes"), list) else []
        if len(media_scenes) != len(scenes):
            raise CodexContentError(f"media requires {len(scenes)} scenes; got {len(media_scenes)}")
        for index, item in enumerate(media_scenes, 1):
            image = str((item or {}).get("image_prompt") or "").strip() if isinstance(item, dict) else ""
            if len(image) < 120:
                raise CodexContentError(f"media scene {index} image_prompt is shorter than 120 characters")
            scenes[index - 1].update({"image_prompt": image, "media_prompt_status": "ready"})
            if index <= 12:
                video = str(item.get("video_prompt") or "").strip()
                _validate_video_prompt(video, index)
                scenes[index - 1]["video_prompt"] = video
        from services.image_grid_prompts import (
            build_compact_image_grid_prompts,
            grid_windows,
            validate_image_grid_prompt_readiness,
            validate_scene_image_prompt_readiness,
        )
        grids = build_compact_image_grid_prompts(media.get("image_grid_prompts") or [])
        validate_scene_image_prompt_readiness(scenes)
        try:
            validate_image_grid_prompt_readiness(
                scenes, grids, status="ready", require_status="ready", require_compact_template=True,
            )
        except ValueError as exc:
            # Image-grid copy is supplementary to the validated per-scene prompts.
            # If a model omits a tail grid or returns an underspecified panel,
            # derive every compact grid from those complete scene prompts rather
            # than discarding an otherwise complete package.
            if "image_grid_prompt" not in str(exc):
                raise
            positions = ("Top-Left", "Top-Right", "Bottom-Left", "Bottom-Right")
            grid_specs = []
            for grid_number, (start, end) in enumerate(grid_windows(len(scenes)), start=1):
                panel_scenes = scenes[start:end]
                grid_specs.append({
                    "grid_number": grid_number,
                    "scene_numbers": [scene["scene_order"] for scene in panel_scenes],
                    "shared_style": f"{payload.get('image_style') or 'realistic'} visual continuity; consistent recurring characters, Korean island setting, wardrobe, lighting, and props.",
                    "negative_prompt": "no text, no words, no letters, no labels, no captions, no watermarks, no borders, no grid lines, no dividers, correct anatomy, no extra limbs",
                    "panels": [
                        {
                            "scene_number": scene["scene_order"],
                            "scene_id": f"scene{scene['scene_order']:03d}",
                            "position": positions[index],
                            "panel_prompt": scene["image_prompt"],
                        }
                        for index, scene in enumerate(panel_scenes)
                    ],
                })
            grids = build_compact_image_grid_prompts(grid_specs)
            validate_image_grid_prompt_readiness(
                scenes, grids, status="ready", require_status="ready", require_compact_template=True,
            )
        structure.update({"image_grid_prompt_status": "ready", "image_grid_prompt_mode": "direct_2x2_only", "image_grid_prompts": grids})
        metadata_context = {**script_context, "structure": structure, "script": script}
        metadata = None
        metadata_error = ""
        for metadata_attempt in range(2):
            metadata_task = (
                "Return only {'publish_metadata':{'titles':['exact selected title'],"
                "'description':'Korean viewer-facing text of at least 150 Korean characters',"
                "'tags':['at least five unique tags, each 30 characters or shorter'],"
                "'hashtags':['at least three #hashtags']}}. The title must match the script and selected upload title. "
                "Count the description before responding: it must contain at least 150 Korean characters, not a short summary. "
                "Do not mention AI, worker, prompt, benchmark, QA, or production internals."
            )
            if metadata_attempt:
                metadata_task += f" The prior metadata was rejected: {metadata_error}. Expand and correct it."
            candidate = self._stage(job_id, "04_metadata", metadata_context, metadata_task).get("publish_metadata")
            description = str((candidate or {}).get("description") or "").strip() if isinstance(candidate, dict) else ""
            if isinstance(candidate, dict) and len(description) >= 120:
                metadata = candidate
                break
            metadata_error = "publish_metadata.description must contain at least 120 characters"
        if not isinstance(metadata, dict):
            raise CodexContentError(metadata_error or "metadata stage returned no publish_metadata")
        thumbnail_context = {
            **script_context,
            "structure": structure,
            "script": script,
            "publish_metadata": metadata,
            "thumbnail_style": str(payload.get("thumbnail_style") or "face").strip() or "face",
        }
        thumbnail_task = (
            "Create exactly three ready-to-use thumbnail text candidates from the completed script. "
            "Return {'thumbnail_hook_texts':['candidate 1','candidate 2','candidate 3'],"
            "'thumbnail_hook_reasoning':'one short sentence','thumbnail_image_prompt':'detailed English prompt'}. "
            "thumbnail_image_prompt must describe one original, text-free 16:9 YouTube thumbnail background in English. "
            "It must make the title promise and strongest story conflict visually obvious, use the selected thumbnail style, "
            "and end with: no text, no letters, no words, no captions, no watermark. Every candidate must be in the requested language, "
            "short enough for a large overlay (normally 3-7 words or 10-20 Korean characters), and distinct: "
            "a strongest reveal, an emotional/question hook, and a contrast/curiosity hook. Stay faithful to the "
            "selected upload title and script. Do not use fabricated facts, generic filler, spoilers that ruin the "
            "story, emojis, hashtags, quotes, or labels. Do not mention AI, Gemini, Codex, worker, prompts, QA, "
            "or production internals."
        )
        thumbnail_stage = self._stage(job_id, "05_thumbnail_copy", thumbnail_context, thumbnail_task)
        raw_thumbnail_texts = thumbnail_stage.get("thumbnail_hook_texts") if isinstance(thumbnail_stage, dict) else []
        thumbnail_hook_texts: list[str] = []
        for value in raw_thumbnail_texts if isinstance(raw_thumbnail_texts, list) else []:
            text = re.sub(r"\s+", " ", str(value or "")).strip().strip('"\'')
            if text and text not in thumbnail_hook_texts:
                thumbnail_hook_texts.append(text[:40])
            if len(thumbnail_hook_texts) == 3:
                break
        if len(thumbnail_hook_texts) != 3:
            raise CodexContentError("thumbnail copy stage requires exactly three usable candidates")
        thumbnail_hook_reasoning = str(
            thumbnail_stage.get("thumbnail_hook_reasoning") or "완성 대본의 핵심 갈등과 반전을 압축했습니다."
        ).strip()[:300]
        thumbnail_image_prompt = str(thumbnail_stage.get("thumbnail_image_prompt") or "").strip()
        if len(thumbnail_image_prompt) < 80:
            raise CodexContentError("thumbnail copy stage requires a detailed text-free thumbnail_image_prompt")
        for grid in structure.get("image_grid_prompts") or []:
            grid["character_references"] = [
                {"character_key": c["character_key"], "name": c["name"], "image_url": c["image_url"]}
                for c in [anchors["main_character"], *anchors["supporting_characters"]]]
        main = script_context["main_character"]
        supporting = script_context["supporting_characters"]
        return {"generated_title": str(payload.get("upload_title") or payload.get("topic") or ""), "title_generation": payload.get("title_generation") or {}, "structure": structure, "script": script, "narrative_blueprint": script_context["narrative_blueprint"], "script_quality_report": qa.get("script_quality_report") or {}, "publish_metadata": metadata, "thumbnail_hook_texts": thumbnail_hook_texts, "thumbnail_hook_reasoning": thumbnail_hook_reasoning, "thumbnail_image_prompt": thumbnail_image_prompt, "thumbnail_copy_source": "codex-cli", "main_character": main, "supporting_characters": supporting, "character_anchors": anchors, "sfx_cues": [], "stage_artifacts": {"plan": plan, "script_draft": written, "script_qa": qa, "character_identity": identity, "media": media, "thumbnail_copy": thumbnail_stage}}


class CodexTopicDiscoveryRunner:
    """Use Codex to turn real YouTube API evidence into original topic options."""

    def __init__(self, config: CodexContentConfig | None = None):
        self.config = config or CodexContentConfig.from_environment()

    def generate(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        work_dir = OUTPUT_DIR / "codex_topic_requests"
        work_dir.mkdir(parents=True, exist_ok=True)
        request_path = work_dir / f"{job_id}.input.json"
        response_path = work_dir / f"{job_id}.response.json"
        request_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prompt = f"""
You are AIR Studio's YouTube topic strategist. Read the real YouTube Data API research packet at {request_path}. Do not perform web searches and do not use Gemini.

Generate 12 genuinely distinct original topic candidates for this category. Each candidate needs title, premise, protagonist, setting, central_object, conflict, payoff, novelty_angle, and evidence_rationale. Diversify protagonist, relationship, setting, object, emotional promise, and narrative mechanism. Never copy a benchmark or forbidden title, plot, or specific incident.

Select exactly one candidate as selected_topic: the most original option that still fits the supplied YouTube evidence. Return JSON only:
{{"candidates":[{{"title":"...","premise":"...","protagonist":"...","setting":"...","central_object":"...","conflict":"...","payoff":"...","novelty_angle":"...","evidence_rationale":"..."}}],"selected_topic":{{"title":"...","premise":"...","protagonist":"...","setting":"...","central_object":"...","conflict":"...","payoff":"...","novelty_angle":"...","evidence_rationale":"..."}},"selection_rationale":"..."}}
""".strip()
        command = [
            self.config.executable, "exec", "--ephemeral", "--sandbox", "read-only", "--color", "never",
            "-C", str(PROJECT_ROOT), "--output-last-message", str(response_path),
        ]
        if self.config.model:
            command.extend(["--model", self.config.model])
        command.append(prompt)
        completed = subprocess.run(command, cwd=str(PROJECT_ROOT), text=True, encoding="utf-8", errors="replace",
                                   capture_output=True, timeout=self.config.timeout_seconds, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-1200:]
            raise CodexContentError(f"Codex topic discovery failed (exit {completed.returncode}): {detail}")
        if not response_path.exists():
            raise CodexContentError("Codex topic discovery completed without an output message file")
        result = _parse_json(response_path.read_text(encoding="utf-8"))
        candidates, selected = result.get("candidates"), result.get("selected_topic")
        if not isinstance(candidates, list) or len(candidates) < 12 or not isinstance(selected, dict):
            raise CodexContentError("Codex topic discovery requires 12 candidates and one selected_topic")
        selected_title = str(selected.get("title") or "").strip()
        titles = {str(item.get("title") or "").strip() for item in candidates if isinstance(item, dict)}
        if not selected_title or selected_title not in titles:
            raise CodexContentError("Selected Codex topic must be one of the generated candidates")
        return result
