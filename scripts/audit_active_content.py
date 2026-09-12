"""Snapshot and audit published/claimed material; never include submitted work."""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.repair_existing_topic_scripts import _headers
import requests

OUT = ROOT / "output" / "active_content_review_20260910"
ACTIVE = {"claimed", "in_progress"}
PROTECTED = {"review_requested", "submitted", "approved", "completed", "paid", "canceled", "cancelled"}


def obj(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def fetch(table, **params):
    url, headers = _headers()
    rows = []
    for offset in range(0, 100000, 500):
        response = requests.get(f"{url}/rest/v1/{table}", headers=headers,
            params={"select": "*", **params, "offset": offset, "limit": 500}, timeout=60)
        response.raise_for_status()
        page = response.json()
        rows.extend(page)
        if len(page) < 500:
            return rows
    raise RuntimeError("Pagination exhausted")


def audit(row):
    structure = obj(row.get("pregenerated_structure"))
    scenes = structure.get("scenes") or []
    metadata = obj(row.get("publish_metadata"))
    issues = []
    if not row.get("pregenerated_script"):
        issues.append("missing_script")
    if not scenes:
        issues.append("missing_scene_structure")
    if row.get("total_scenes") and len(scenes) != row["total_scenes"]:
        issues.append("scene_count_mismatch")
    for key, target in (("image_prompt", scenes), ("video_prompt", scenes[:12])):
        missing = [i for i, scene in enumerate(target, 1) if not str(scene.get(key) or "").strip()]
        if missing:
            issues.append(f"missing_{key}:{missing}")
        counts = Counter(str(s.get(key) or "").strip() for s in target)
        if any(v > 1 for k, v in counts.items() if k):
            issues.append(f"duplicate_{key}")
    if len(str(metadata.get("description") or "")) < 120:
        issues.append("missing_or_short_description")
    if not metadata.get("tags"):
        issues.append("missing_tags")
    report = obj(row.get("script_quality_report"))
    if report.get("profile") != "senior_listening_v3":
        issues.append("no_current_senior_review")
    return {"id": row["id"], "title": row.get("generated_title") or row.get("topic"),
        "status": row.get("status"), "category_id": row.get("category_id"), "scenes": len(scenes),
        "script_chars": len(str(row.get("pregenerated_script") or "")),
        "images": sum(bool(s.get("image_url") or s.get("image_path")) for s in scenes),
        "issues": issues}


def write_report():
    inventory = json.loads((OUT / "inventory.json").read_text(encoding="utf-8"))
    snapshot = json.loads((OUT / "source_snapshot.json").read_text(encoding="utf-8"))
    result_path = OUT / "run_results.json"
    results = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    decisions_path = OUT / "pending_decisions.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8")) if decisions_path.exists() else {}
    labels = {"duplicate_video_prompt": "영상 프롬프트 중복", "duplicate_image_prompt": "이미지 프롬프트 중복",
        "no_current_senior_review": "최신 독립 검수 기록 없음", "missing_image_prompt": "이미지 프롬프트 누락",
        "missing_video_prompt": "영상 프롬프트 누락", "missing_script": "대본 없음", "missing_scene_structure": "씬 구조 없음",
        "missing_or_short_description": "설명 누락/부족", "missing_tags": "태그 없음", "duplicate_title_in_queue": "주제 제목 중복"}
    lines = ["# 공개·진행 중 토픽 재점검", "", "점검 기준: senior_listening_v3 + 카테고리별 문체 + 씬별 이미지/영상 프롬프트 + 게시 메타데이터.", "",
        "공개·배정 후보 63개를 조회했다. 제목만 있고 본문이 없는 행도 있으므로 63개 모두 완성 토픽이라는 뜻은 아니다.",
        "제출/검수대기·완료 프로젝트는 수정 대상에서 제외한다. 조회 시 3340에 검수 대기 프로젝트가 연결되어 있어 원본도 보호한다.",
        "topic_queue_id가 없는 진행 중 ‘한쪽 귀만 달린 호랑이 가면’ 사본은 연결을 추정하여 덮어쓰지 않는다.", "",
        "기계 점검의 문제 없음은 작품 품질 통과를 뜻하지 않는다. 이미지 파일의 실제 화소를 검수했다는 뜻도 아니다.", "",
        "## 건별 현황", "", "| ID | 주제 | 씬 | 1차 발견 사항 | 수정 상태 |", "|---|---|---:|---|---|"]
    for row in inventory:
        issues = ", ".join(dict.fromkeys(labels.get(i.split(":")[0], i) for i in row["issues"])) or "기계 점검상 누락 없음; 내용 검수 필요"
        status = results.get(str(row["id"]), {}).get("status", "대기")
        status = {"saved_and_verified": "수정 저장·재조회 검증 완료", "candidate_approved": "수정안 검수 통과·미저장",
            "reviewing": "검수/교정 중", "blocked": "보류·추가 확인 필요"}.get(status, status)
        if str(row["id"]) in decisions:
            status = "사용자 요청으로 제외" if decisions[str(row["id"])].startswith("Excluded by user") else "영상 길이 확인 대기"
        narration_result = OUT / f"{row['id']}_original_narration_result.json"
        if narration_result.exists() and json.loads(narration_result.read_text(encoding="utf-8")).get("status") == "narration_saved_and_verified":
            status = "원본 기준 대본 저장 검증 완료 · 프롬프트는 기존값 보존"
        lines.append(f"| {row['id']} | {row['title'].replace('|', '/')} | {row['scenes']} | {issues} | {status} |")
    projects = {p["id"]: p for p in snapshot["projects"] + snapshot["unlinked_active_projects"]}
    separate = [(projects[k], value) for k,value in results.items() if k in projects]
    if separate:
        lines += ["", "## 현재 편집본 별도 교정", ""]
        for project, result in separate:
            lines.append(f"- {project['title']}: {result['status']}")
    lines += ["", "## 저장 원칙", "", "수정본과 독립 검수 결과를 먼저 파일로 만든다. 통과 후 기존 DB 값을 백업하고, 제출 여부·동시 수정 여부를 재확인한다.",
        "진행 중 프로젝트는 주제 원본, 프로젝트 원본 사본, 편집용 대본/씬, 씬별 프롬프트를 함께 맞춘다. 기존 이미지·업로드 영상·담당자·완료 상태는 바꾸지 않는다.",
        "사용자 대본/자막 편집이 감지되면 해당 수정본의 자동 반영을 보류한다. 수정 후 음성은 재생성이 필요하며 이전 자료는 백업한다.",
        "여러 테이블 저장은 REST 단위 작업이므로 중간 충돌 시 부분 저장 가능성을 기록한다. 저장 이력과 재조회 검증을 근거로 완료 여부를 판단한다.", ""]
    (OUT / "점검현황.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    topics = fetch("topics_queue", status="in.(pending,assigned,in_progress,claimed)", order="id.desc")
    projects = fetch("std_projects", order="id.asc")
    linked = {p.get("topic_queue_id") for p in projects if p.get("status") in ACTIVE}
    protected = {p.get("topic_queue_id") for p in projects if p.get("status") in PROTECTED}
    selected = [t for t in topics if t.get("id") not in protected and (
        t.get("id") in linked or (t.get("generated_title") and t.get("status") in {"pending", "assigned"}))]
    ids = {t["id"] for t in selected}
    relevant_projects = [p for p in projects if p.get("topic_queue_id") in ids and p.get("status") in ACTIVE]
    snapshot = {"topics": selected, "projects": relevant_projects,
        "categories": fetch("categories"), "characters": fetch("topic_character_assets"),
        "protected_topic_ids": sorted(x for x in protected if x is not None),
        "unlinked_active_projects": [p for p in projects if p.get("status") in ACTIVE and not p.get("topic_queue_id")]}
    path = OUT / "source_snapshot.json"
    if path.exists():
        raise RuntimeError("Snapshot already exists; preserve the original")
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    results = [audit(t) for t in selected]
    title_counts = Counter(t.get("generated_title") for t in selected)
    for result in results:
        if title_counts[result["title"]] > 1:
            result["issues"].append("duplicate_title_in_queue")
    (OUT / "inventory.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report()
    print(json.dumps({"topics": len(selected), "active_projects": len(relevant_projects),
        "protected_topics": snapshot["protected_topic_ids"],
        "unlinked_active_projects": [{"id": p["id"], "title": p.get("title")} for p in snapshot["unlinked_active_projects"]],
        "issue_counts": Counter(issue.split(":")[0] for row in results for issue in row["issues"]),
        "inventory": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
