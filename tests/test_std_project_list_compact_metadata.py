from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STD_PAGE = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")
PROJECTS_ROUTE = (ROOT / "auth-web" / "app" / "api" / "std" / "projects" / "route.ts").read_text(encoding="utf-8")
SUBMIT_ROUTE = (ROOT / "auth-web" / "app" / "api" / "std" / "projects" / "[projectId]" / "submit" / "route.ts").read_text(encoding="utf-8")


def test_project_list_uses_compact_start_and_submission_dates():
    assert "const formatProjectListDate = (value: unknown): string" in STD_PAGE
    assert "${twoDigits(date.getHours())}:${twoDigits(date.getMinutes())}" in STD_PAGE
    assert "{formatProjectListDate(p.created_at)}" in STD_PAGE
    assert "const submittedAt = p.submitted_at || p.shared_submission?.submitted_at" in STD_PAGE
    assert "{formatProjectListDate(submittedAt)}" in STD_PAGE
    assert "p.updated_at ? p.updated_at.slice" not in STD_PAGE
    assert "const isSubmitted = Boolean(p.submitted_at)" in STD_PAGE
    assert "created_at,updated_at,submitted_at,progress_payload" in PROJECTS_ROUTE


def test_same_topic_submission_is_shared_without_duplicate_rendering():
    assert "shared_submission" in PROJECTS_ROUTE
    assert ".in('topic_queue_id', topicQueueIds)" in PROJECTS_ROUTE
    assert "shared_submission: true" in SUBMIT_ROUTE
    assert ".eq('topic_queue_id', project.topic_queue_id)" in SUBMIT_ROUTE
    assert "공동 작업 제출 완료" in STD_PAGE
    assert "const hasSharedSubmission = Boolean(p.shared_submission)" in STD_PAGE
    assert ") : (pStatus.allDone || hasSharedSubmission) ?" in STD_PAGE


def test_project_list_shows_a_compact_saved_thumbnail_first():
    assert "<th className=\"px-2 py-2.5 w-12 text-center\">썸네일</th>" in STD_PAGE
    assert "const projectThumbnailUrl = sanitizeAssetUrl(" in STD_PAGE
    assert "w-9 h-7 object-cover rounded" in STD_PAGE
