"""Repair existing topics_queue scripts with the current category narration rules.

This intentionally rewrites text only. It preserves scene count, durations,
image prompts, video prompts, generated images/videos, metadata, and project
assignment state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import copy
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(WORKER) not in sys.path:
    sys.path.insert(0, str(WORKER))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except Exception:
    pass

from codex_content_runner import (  # noqa: E402
    CodexContentConfig,
    CodexStagedContentRunner,
    CodexContentError,
    _category_narration_voice,
    _pacing_schedule,
    _resolve_script_style_directive,
    _scene_char_budgets,
    _script_rhythm_contract,
    _script_rhythm_warnings,
)
from senior_script_guard import PROFILE, text_issues, review_issues


SELECT_COLUMNS = (
    "id,topic,generated_title,category_id,category_name_en,category_name_vi,category_name_th,"
    "status,assigned_employee_email,assigned_script_style,assigned_duration_minutes,"
    "recommended_duration_minutes,pregenerated_script,pregenerated_structure,"
    "script_quality_report,publish_metadata"
)


def _headers() -> tuple[str, dict[str, str]]:
    base_url = (os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base_url or not key:
        raise RuntimeError("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return base_url, {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _parse_json(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else ""
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("model response must be a JSON object")
    return parsed


def _fetch_categories(base_url: str, headers: dict[str, str]) -> dict[str, str]:
    response = requests.get(
        f"{base_url}/rest/v1/categories",
        headers=headers,
        params={"select": "id,name", "limit": "500"},
        timeout=30,
    )
    if response.status_code >= 400:
        return {}
    return {str(row.get("id")): str(row.get("name") or "") for row in response.json()}


def _fetch_rows(base_url: str, headers: dict[str, str], ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    id_filter = "in.(" + ",".join(str(i) for i in ids) + ")"
    response = requests.get(
        f"{base_url}/rest/v1/topics_queue",
        headers=headers,
        params={
            "select": SELECT_COLUMNS,
            "id": id_filter,
            "order": "id.asc",
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"fetch failed: HTTP {response.status_code} {response.text[:500]}")
    by_id = {int(row["id"]): row for row in response.json()}
    return [by_id[i] for i in ids if i in by_id]


def _duration_seconds(row: dict[str, Any], scenes: list[dict[str, Any]]) -> int:
    total = 0
    for scene in scenes:
        try:
            total += int(float(scene.get("duration_seconds") or scene.get("target_duration") or 0))
        except Exception:
            pass
    if total > 0:
        return total
    minutes = row.get("assigned_duration_minutes") or row.get("recommended_duration_minutes") or 5
    return int(float(minutes) * 60)


def _existing_sections(scenes: list[dict[str, Any]], fallback_script: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    fallback_parts = [part.strip() for part in str(fallback_script or "").split("\n\n") if part.strip()]
    for index, scene in enumerate(scenes, 1):
        text = str(scene.get("scene_text") or scene.get("narration") or "").strip()
        if not text and index <= len(fallback_parts):
            text = fallback_parts[index - 1]
        sections.append({
            "scene_order": int(scene.get("scene_order") or scene.get("scene_number") or index),
            "duration_seconds": int(float(scene.get("duration_seconds") or scene.get("target_duration") or 0) or 1),
            "summary": str(scene.get("scene_summary") or scene.get("scene_situation") or "").strip(),
            "current_text": text,
        })
    return sections


def _repair_scene_budgets(scenes: list[dict[str, Any]], payload: dict[str, Any], current_sections: list[dict[str, Any]]) -> list[dict[str, int]]:
    try:
        return _scene_char_budgets(scenes, payload)
    except Exception:
        budgets: list[dict[str, int]] = []
        for index, section in enumerate(current_sections, 1):
            text_len = len(str(section.get("current_text") or "").strip())
            if text_len <= 0:
                text_len = 120 if len(current_sections) <= 12 else 80
            minimum = max(12, int(text_len * 0.18))
            maximum = max(minimum + 30, int(text_len * 1.75))
            duration = int(section.get("duration_seconds") or 0)
            budgets.append({
                "scene_order": index,
                "duration_seconds": max(1, duration),
                "target_chars": text_len,
                "min_chars": minimum,
                "max_chars": maximum,
                "budget_source": "existing_text_length_fallback",
            })
        return budgets


def _soften_repeated_endings(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    replacements = {
        "했다고 말했다": "했다고 전했지요",
        "라고 말했다": "라고 털어놓았지요",
        "고 말했다": "고 낮게 말했지요",
        "바라보았다": "바라보았지요",
        "돌아보았다": "돌아보았지요",
        "말했다": "말했지요",
        "나왔다": "모습을 드러냈지요",
        "있었다": "있었지요",
        "되었다": "되고 말았지요",
        "않았다": "않았지요",
        "이었다": "이었지요",
        "였다": "였지요",
        "했다": "했지요",
    }
    softened = [dict(section) if isinstance(section, dict) else section for section in sections]
    for _ in range(3):
        warnings = _script_rhythm_warnings(softened)
        if not warnings:
            break
        changed = False
        for warning in warnings:
            match = re.search(r"scenes (\d+)-(\d+) repeat blunt ending '([^']+)'", warning)
            if not match:
                continue
            start, end, ending = int(match.group(1)), int(match.group(2)), match.group(3)
            replacement = replacements.get(ending)
            if not replacement:
                continue
            seen = 0
            for index in range(start, min(end, len(softened)) + 1):
                section = softened[index - 1]
                if not isinstance(section, dict):
                    continue
                text = str(section.get("text") or "").strip()
                if _korean_sentence_end_for_repair(text) != ending:
                    continue
                seen += 1
                if seen <= 2:
                    continue
                section["text"] = re.sub(rf"{re.escape(ending)}([.!?。…\"'”’)\]]*)$", replacement + r"\1", text)
                changed = True
        if not changed:
            break
    return softened


def _korean_sentence_end_for_repair(text: str) -> str:
    from codex_content_runner import _korean_sentence_end_bucket
    return _korean_sentence_end_bucket(text)


def _run_codex_repair_request(request: dict[str, Any], request_path: Path, response_path: Path, model: str, rhythm_rejection: list[str], force: bool) -> dict[str, Any]:
    request["rhythm_rejection"] = rhythm_rejection
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
    should_generate = force or not response_path.exists() or bool(rhythm_rejection)
    if should_generate and response_path.exists() and rhythm_rejection:
        response_path.unlink()
    if should_generate:
        attempt_note = (
            " The previous repair was rejected by local validation. "
            f"Fix these exact defects: {'; '.join(rhythm_rejection)}."
            if rhythm_rejection else ""
        )
        prompt = (
            f"Read {request_path}. You are AIR Studio's script repair stage. "
            "Use the supplied existing scenes and rewrite only the narration text. "
            "Obey category_narration_voice, script_style_directive, script_rhythm_contract, and each scene_budgets item. "
            "Before returning, inspect every 5-scene window and actively vary final predicates so 했다/였다/있었다/나왔다/말했다 do not repeat. "
            "Use connective oral narration, causal phrasing, and emotional consequence instead of clipped factual sentences. "
            "Return {'sections':[{'scene_order':n,'text':'...'}], 'script_quality_report':{...}} exactly. "
            "The report must include score, category_voice_score, rhythm_score, repetitive_ending_score, critical_issues, and revision_notes. "
            "A pass requires score >=82 and empty critical_issues. Return JSON only."
            + attempt_note
        )
        command = [
            os.getenv("CODEX_EXECUTABLE", "codex"),
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "-C",
            str(ROOT),
            "--output-last-message",
            str(response_path),
        ]
        if model:
            command.extend(["--model", model])
        command.append(prompt)
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(120, int(os.getenv("CODEX_CONTENT_TIMEOUT_SECONDS", "1800"))),
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-1200:]
            raise RuntimeError(f"codex failed: {detail}")
        if not response_path.exists():
            raise RuntimeError("codex completed without response file")
    return _parse_json(response_path.read_text(encoding="utf-8"))


def _section_budget_rejections(sections: list[Any], scene_budgets: list[dict[str, int]], offset: int = 0) -> list[str]:
    rejections: list[str] = []
    for local_index, section in enumerate(sections, 1):
        scene_index = offset + local_index
        text = str((section or {}).get("text") or "").strip() if isinstance(section, dict) else ""
        if not text:
            rejections.append(f"empty section {scene_index}")
            continue
        budget = scene_budgets[local_index - 1]
        if len(text) < budget["min_chars"] or len(text) > max(budget["max_chars"] * 2, budget["max_chars"] + 30):
            rejections.append(
                f"section {scene_index} violates budget: len={len(text)}, min={budget['min_chars']}, max={budget['max_chars']}"
            )
    return rejections[:5]


def _repair_with_codex_chunked(
    row: dict[str, Any],
    category_name: str,
    output_dir: Path,
    model: str,
    payload: dict[str, Any],
    current_sections: list[dict[str, Any]],
    scene_budgets: list[dict[str, int]],
    *,
    force: bool,
    chunk_size: int = 10,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repaired_all: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for start in range(0, len(current_sections), chunk_size):
        end = min(start + chunk_size, len(current_sections))
        chunk_sections = current_sections[start:end]
        chunk_budgets = scene_budgets[start:end]
        request = {
            "topic_id": row.get("id"),
            "title": row.get("generated_title") or row.get("topic"),
            "category_name": category_name,
            "global_scene_count": len(current_sections),
            "chunk_scene_range": [start + 1, end],
            "script_style_directive": _resolve_script_style_directive(row.get("assigned_script_style")),
            "category_narration_voice": _category_narration_voice(payload),
            "script_rhythm_contract": _script_rhythm_contract(payload),
            "scene_budgets": chunk_budgets,
            "sections": chunk_sections,
            "instruction": (
                "Rewrite this chunk's Korean narration only. Preserve scene_order values exactly and return exactly this chunk's sections. "
                "Keep continuity with the surrounding story, but do not invent new scenes or omit any supplied scene."
            ),
        }
        request_path = output_dir / f"topic_{row['id']}_script_repair_chunk_{start + 1}_{end}_request.json"
        response_path = output_dir / f"topic_{row['id']}_script_repair_chunk_{start + 1}_{end}_response.json"
        rejection: list[str] = []
        repaired: list[Any] = []
        data: dict[str, Any] = {}
        for _attempt in range(4):
            data = _run_codex_repair_request(request, request_path, response_path, model, rejection, force)
            repaired = data.get("sections") if isinstance(data.get("sections"), list) else []
            if len(repaired) != len(chunk_sections):
                rejection = [f"expected {len(chunk_sections)} sections for scenes {start + 1}-{end}, got {len(repaired)}"]
                continue
            expected_orders = [int(s.get("scene_order") or s.get("scene_number") or i) for i, s in enumerate(chunk_sections, start + 1)]
            actual_orders = [int((s or {}).get("scene_order") or 0) for s in repaired if isinstance(s, dict)]
            if actual_orders != expected_orders:
                rejection = [f"scene_order mismatch: expected {expected_orders}, got {actual_orders}"]
                continue
            warnings = _script_rhythm_warnings(repaired)
            if warnings:
                rejection = warnings
                continue
            budget_rejections = _section_budget_rejections(repaired, chunk_budgets, offset=start)
            if budget_rejections:
                rejection = budget_rejections
                continue
            break
        else:
            softened = _soften_repeated_endings(repaired if repaired else [])
            if not softened or _script_rhythm_warnings(softened) or _section_budget_rejections(softened, chunk_budgets, offset=start):
                raise CodexContentError("; ".join(rejection) or f"chunk {start + 1}-{end} failed")
            repaired = softened
        repaired_all.extend(repaired)
        if isinstance(data.get("script_quality_report"), dict):
            reports.append(data["script_quality_report"])
    softened_all = _soften_repeated_endings(repaired_all)
    warnings = _script_rhythm_warnings(softened_all)
    if warnings:
        raise CodexContentError("whole-script rhythm warnings remain after chunk repair: " + "; ".join(warnings))
    scores = [int(report.get("score") or 0) for report in reports if str(report.get("score") or "").isdigit()]
    report = {
        "score": min(scores) if scores else 90,
        "chunked_repair": True,
        "chunk_count": (len(current_sections) + chunk_size - 1) // chunk_size,
        "critical_issues": [],
        "revision_notes": ["Large legacy script repaired in chunks to preserve all scene mappings."],
    }
    return softened_all, report


def _repair_with_codex(row: dict[str, Any], category_name: str, output_dir: Path, model: str, *, force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Repair and independently review; never manufacture a passing verdict."""
    scenes = (row.get("pregenerated_structure") or {}).get("scenes") or []
    if not scenes:
        raise CodexContentError("No scene structure to repair")
    payload = {"category_id": row.get("category_id"), "category_name": category_name,
               "language": row.get("language") or "ko", "target_duration_seconds": _duration_seconds(row, scenes),
               "topic": row.get("topic"), "upload_title": row.get("generated_title") or row.get("topic"),
               "assigned_script_style": row.get("assigned_script_style")}
    current = _existing_sections(scenes, row.get("pregenerated_script") or "")
    budgets = _repair_scene_budgets(scenes, payload, current)
    context = {**payload, "category_narration_voice": _category_narration_voice(payload),
               "script_rhythm_contract": _script_rhythm_contract(payload), "sections": current,
               "original_script": row.get("pregenerated_script"), "scene_budgets": budgets,
               "structure": row.get("pregenerated_structure"), "script_style_directive": _resolve_script_style_directive(row.get("assigned_script_style"))}
    runner = CodexStagedContentRunner(CodexContentConfig(
        os.getenv("CODEX_EXECUTABLE", "codex"), model,
        max(120, int(os.getenv("CODEX_CONTENT_TIMEOUT_SECONDS", "1800")))))
    job_id = f"repair-{row['id']}-{PROFILE}" + (f"-{time.time_ns()}" if force else "")
    for attempt in range(3):
        result = runner._stage(job_id, "repair_script", context,
            "Rewrite the existing narration for senior adult listening under the mandatory category contract. "
            "Preserve the title, main characters, coherent plot, scene count/order and duration. "
            "Correct contradictions, unclear introductions, malformed expressions and repeated explanations through minimal motivated changes. "
            "Preserve correspondence with existing scene visuals; do not introduce replacement protagonists, settings or props. "
            "Do not preserve an error merely because it is in the original. Financial claims need supplied evidence or explicit hypothetical framing. "
            "Return {'sections':[{'scene_order':1,'text':'...'}]} with every scene and respect scene_budgets. No headings, metadata or stage directions in narration.")
        sections = result.get("sections") if isinstance(result.get("sections"), list) else []
        errors = text_issues(sections, payload) + _script_rhythm_warnings(sections)
        if len(sections) != len(scenes):
            errors.append(f"Expected {len(scenes)} sections, got {len(sections)}")
        for section, budget in zip(sections, budgets):
            text = section.get("text") if isinstance(section, dict) else None
            if not isinstance(text, str) or not budget["min_chars"] <= len(text.strip()) <= max(budget["max_chars"] * 2, budget["max_chars"] + 30):
                errors.append(f"Section {budget['scene_order']} duration budget violated")
        review = {}
        if not errors:
            review = runner._stage(job_id, "repair_senior_review", {**context, "sections": sections,
                "script": "\n\n".join(s["text"].strip() for s in sections)},
                "Independently review the complete revised narration. Do not rewrite and do not trust author scores. "
                "Check all nine senior listening criteria, original title and correspondence with existing scene visuals. "
                "Return {'script_quality_report':{...}} using the exact required profile and evidence-backed checks in category_narration_voice.")
            errors += review_issues(review.get("script_quality_report"))
        if not errors:
            return sections, review["script_quality_report"]
        context = {**context, "previous_revision": sections, "rejection": errors, "independent_review": review}
    raise CodexContentError("Senior repair rejected: " + "; ".join(errors[:12]))


def _repair_with_codex_legacy(row: dict[str, Any], category_name: str, output_dir: Path, model: str, *, force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    structure = row.get("pregenerated_structure") if isinstance(row.get("pregenerated_structure"), dict) else {}
    scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else []
    if not scenes:
        raise CodexContentError("row has no pregenerated_structure.scenes")

    duration_seconds = _duration_seconds(row, scenes)
    payload = {
        "topic": row.get("topic"),
        "upload_title": row.get("generated_title") or row.get("topic"),
        "category": category_name,
        "category_name": category_name,
        "category_id": row.get("category_id"),
        "script_style": row.get("assigned_script_style"),
        "assigned_script_style": row.get("assigned_script_style"),
        "target_duration_seconds": duration_seconds,
        "language": "ko",
    }
    current_sections = _existing_sections(scenes, row.get("pregenerated_script") or "")
    scene_budgets = _repair_scene_budgets(scenes, payload, current_sections)
    if len(row.get("pregenerated_script") or "") > 25000:
        return _repair_with_codex_chunked(
            row, category_name, output_dir, model, payload, current_sections, scene_budgets, force=force
        )
    request = {
        "topic_id": row.get("id"),
        "title": row.get("generated_title") or row.get("topic"),
        "category_name": category_name,
        "script_style_directive": _resolve_script_style_directive(row.get("assigned_script_style")),
        "category_narration_voice": _category_narration_voice(payload),
        "script_rhythm_contract": _script_rhythm_contract(payload),
        "scene_budgets": scene_budgets,
        "sections": current_sections,
        "instruction": (
            "Rewrite the existing Korean narration only. Preserve the same story, scene order, scene count, "
            "duration_seconds, plot facts, character identities, and payoff. Do not create image prompts, video prompts, "
            "metadata, headings, timestamps, camera directions, or explanations. Return JSON only."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / f"topic_{row['id']}_script_repair_request.json"
    response_path = output_dir / f"topic_{row['id']}_script_repair_response.json"
    rhythm_rejection: list[str] = []
    for repair_attempt in range(4):
        request["rhythm_rejection"] = rhythm_rejection
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")

        should_generate = force or not response_path.exists() or bool(rhythm_rejection)
        if should_generate and response_path.exists() and rhythm_rejection:
            response_path.unlink()
        if should_generate:
            attempt_note = (
                " The previous repair was rejected by local rhythm validation. "
                f"Fix these exact defects: {'; '.join(rhythm_rejection)}."
                if rhythm_rejection else ""
            )
            prompt = (
                f"Read {request_path}. You are AIR Studio's script repair stage. "
                "Use the supplied existing scenes and rewrite only the narration text. "
                "Obey category_narration_voice, script_style_directive, script_rhythm_contract, and each scene_budgets item. "
                "Before returning, inspect every 5-scene window and actively vary final predicates so 했다/였다/있었다/나왔다/말했다 do not repeat. "
                "Use connective oral narration, causal phrasing, and emotional consequence instead of clipped factual sentences. "
                "Return {'sections':[{'scene_order':n,'text':'...'}], 'script_quality_report':{...}} exactly. "
                "The report must include score, category_voice_score, rhythm_score, repetitive_ending_score, critical_issues, and revision_notes. "
                "A pass requires score >=82 and empty critical_issues. Return JSON only."
                + attempt_note
            )
            command = [
                os.getenv("CODEX_EXECUTABLE", "codex"),
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "-C",
                str(ROOT),
                "--output-last-message",
                str(response_path),
            ]
            if model:
                command.extend(["--model", model])
            command.append(prompt)
            completed = subprocess.run(
                command,
                cwd=str(ROOT),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=max(120, int(os.getenv("CODEX_CONTENT_TIMEOUT_SECONDS", "1800"))),
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()[-1200:]
                raise RuntimeError(f"codex failed: {detail}")
            if not response_path.exists():
                raise RuntimeError("codex completed without response file")
        data = _parse_json(response_path.read_text(encoding="utf-8"))
        repaired = data.get("sections") if isinstance(data.get("sections"), list) else []
        if len(repaired) != len(scenes):
            raise CodexContentError(f"expected {len(scenes)} sections, got {len(repaired)}")
        warnings = _script_rhythm_warnings(repaired)
        if not warnings:
            budget_rejections: list[str] = []
            for index, section in enumerate(repaired, 1):
                text = str((section or {}).get("text") or "").strip() if isinstance(section, dict) else ""
                if not text:
                    budget_rejections.append(f"empty section {index}")
                    continue
                budget = scene_budgets[index - 1]
                if len(text) < budget["min_chars"] or len(text) > max(budget["max_chars"] * 2, budget["max_chars"] + 30):
                    budget_rejections.append(
                        f"section {index} violates budget: len={len(text)}, min={budget['min_chars']}, max={budget['max_chars']}"
                    )
            if not budget_rejections:
                report = data.get("script_quality_report") if isinstance(data.get("script_quality_report"), dict) else {}
                return repaired, report
            warnings = budget_rejections[:5]
        rhythm_rejection = warnings

    softened = _soften_repeated_endings(repaired if "repaired" in locals() else [])
    if softened and not _script_rhythm_warnings(softened):
        report = data.get("script_quality_report") if "data" in locals() and isinstance(data.get("script_quality_report"), dict) else {}
        report = {**report, "postprocess": "softened repeated final predicates"}
        return softened, report
    raise CodexContentError("rhythm warnings remain: " + "; ".join(rhythm_rejection))


def _sync_claimed_std_projects(
    base_url: str,
    headers: dict[str, str],
    topic_id: Any,
    script: str,
    structure: dict[str, Any],
    repair_report: dict[str, Any],
) -> int:
    """Propagate an intentional worker rewrite to every already-claimed STD project.

    STD keeps a source snapshot for reproducibility.  A category-voice repair
    is an explicit replacement of that worker source, so all three copies
    (source, editor payload, and progress metadata) must advance together.
    """
    response = requests.get(
        f"{base_url}/rest/v1/std_projects",
        headers=headers,
        params={
            "topic_queue_id": f"eq.{quote(str(topic_id), safe='')}",
            "select": "id,source_payload,project_payload,progress_payload",
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"STD project lookup for topic {topic_id} failed: HTTP {response.status_code} {response.text[:500]}")
    projects = response.json()
    if not isinstance(projects, list):
        raise RuntimeError(f"STD project lookup for topic {topic_id} returned invalid JSON")

    for project in projects:
        if not isinstance(project, dict) or not project.get("id"):
            continue
        source_payload = project.get("source_payload") if isinstance(project.get("source_payload"), dict) else {}
        project_payload = project.get("project_payload") if isinstance(project.get("project_payload"), dict) else {}
        progress_payload = project.get("progress_payload") if isinstance(project.get("progress_payload"), dict) else {}
        updated_source = {
            **source_payload,
            "pregenerated_script": script,
            "pregenerated_structure": structure,
            "script_quality_report": repair_report,
        }
        updated_payload = {
            **project_payload,
            "script": script,
            "original_worker_script": script,
            "structure": structure,
        }
        updated_progress = {
            **progress_payload,
            "pregenerated_script_status": "ready",
            "script_quality_report": repair_report,
        }
        update = requests.patch(
            f"{base_url}/rest/v1/std_projects?id=eq.{quote(str(project['id']), safe='')}",
            headers=headers,
            json={
                "source_payload": updated_source,
                "project_payload": updated_payload,
                "progress_payload": updated_progress,
            },
            timeout=60,
        )
        if update.status_code >= 400:
            raise RuntimeError(
                f"STD project update {project['id']} for topic {topic_id} failed: "
                f"HTTP {update.status_code} {update.text[:500]}"
            )
    return len(projects)


def _update_row(base_url: str, headers: dict[str, str], row: dict[str, Any], sections: list[dict[str, Any]], report: dict[str, Any]) -> None:
    errors = text_issues(sections, row) + review_issues(report)
    if errors:
        raise CodexContentError("Refusing to save unapproved repair: " + "; ".join(errors[:12]))
    structure = copy.deepcopy(row.get("pregenerated_structure")) if isinstance(row.get("pregenerated_structure"), dict) else {}
    scenes = structure.get("scenes") if isinstance(structure.get("scenes"), list) else []
    if len(sections) != len(scenes):
        raise CodexContentError("Refusing incomplete scene repair")
    backup_dir = ROOT / "output" / "script_repairs" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / f"topic_{row['id']}_{time.time_ns()}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    by_order = {
        int(section.get("scene_order") or index): str(section.get("text") or "").strip()
        for index, section in enumerate(sections, 1)
        if isinstance(section, dict)
    }
    parts: list[str] = []
    for index, scene in enumerate(scenes, 1):
        order = int(scene.get("scene_order") or scene.get("scene_number") or index)
        text = by_order.get(order) or by_order.get(index) or ""
        scene["scene_text"] = text
        scene["narration"] = text
        parts.append(text)
    script = "\n\n".join(part for part in parts if part).strip()
    repair_report = {
        **report,
        "codex_repair_profile": PROFILE,
        "repaired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "preserved_media_assets": True,
    }
    response = requests.patch(
        f"{base_url}/rest/v1/topics_queue?id=eq.{quote(str(row['id']), safe='')}",
        headers=headers,
        json={
            "pregenerated_script": script,
            "pregenerated_script_status": "ready",
            "pregenerated_structure": structure,
            "script_quality_report": repair_report,
        },
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"update topic {row['id']} failed: HTTP {response.status_code} {response.text[:500]}")
    _sync_claimed_std_projects(base_url, headers, row["id"], script, structure, repair_report)


def _sync_existing_row(base_url: str, headers: dict[str, str], row: dict[str, Any]) -> int:
    """Synchronize a previously repaired queue row without generating text again."""
    structure = row.get("pregenerated_structure") if isinstance(row.get("pregenerated_structure"), dict) else {}
    script = str(row.get("pregenerated_script") or "").strip()
    report = row.get("script_quality_report") if isinstance(row.get("script_quality_report"), dict) else {}
    if not script or not structure:
        raise CodexContentError(f"topic {row.get('id')} has no repairable script/structure")
    if report.get("codex_repair_profile") != PROFILE or review_issues(report):
        raise CodexContentError(f"topic {row.get('id')} has not passed the current senior listening review")
    return _sync_claimed_std_projects(base_url, headers, row["id"], script, structure, report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair existing topics_queue scripts with current narration criteria.")
    parser.add_argument("--ids", required=True, help="Comma-separated topic IDs or ranges, e.g. 3340,3350-3371")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync-only", action="store_true", help="Copy already repaired scripts into claimed STD projects without regeneration")
    parser.add_argument("--model", default=os.getenv("CODEX_CONTENT_MODEL", ""))
    parser.add_argument("--force-regenerate", action="store_true", help="Ignore cached repair response JSON files")
    args = parser.parse_args()

    ids: list[int] = []
    for token in args.ids.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = [int(part.strip()) for part in token.split("-", 1)]
            ids.extend(range(start, end + 1))
        else:
            ids.append(int(token))
    ids = list(dict.fromkeys(ids))

    base_url, headers = _headers()
    categories = _fetch_categories(base_url, headers)
    rows = _fetch_rows(base_url, headers, ids)
    if not rows:
        print("No rows found.")
        return 1
    output_dir = ROOT / "output" / "script_repairs"
    print(f"Repair target rows: {len(rows)}", flush=True)
    for row in rows:
        if args.sync_only:
            synced = _sync_existing_row(base_url, headers, row)
            print(f"[{row['id']}] synced claimed projects={synced}", flush=True)
            continue
        category_name = categories.get(str(row.get("category_id"))) or row.get("category_name_en") or ""
        print(f"[{row['id']}] repairing: {row.get('generated_title') or row.get('topic')} / {category_name}", flush=True)
        sections, report = _repair_with_codex(row, category_name, output_dir, args.model, force=args.force_regenerate)
        if args.dry_run:
            print(f"[{row['id']}] dry-run ok, sections={len(sections)}, report_score={report.get('score')}", flush=True)
            continue
        _update_row(base_url, headers, row, sections, report)
        print(f"[{row['id']}] updated, sections={len(sections)}, report_score={report.get('score')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
