from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_std_claim_rejects_topic_with_existing_project():
    source = (ROOT / "auth-web" / "app" / "api" / "std" / "topics" / "[topicId]" / "claim" / "route.ts").read_text(encoding="utf-8")

    assert ".from('std_projects')" in source
    assert ".eq('topic_queue_id', topicId)" in source
    assert "Topic already claimed" in source
    assert "project_id: existingProject.id" in source


def test_std_claim_closes_all_recommendation_cache_rows():
    source = (ROOT / "auth-web" / "app" / "api" / "std" / "topics" / "[topicId]" / "claim" / "route.ts").read_text(encoding="utf-8")

    assert ".from('user_topic_recommendations')" in source
    assert ".update({ is_claimed: true, claimed_at: new Date().toISOString() })" in source
    assert ".eq('topic_queue_id', topicId)" in source


def test_std_recommendations_exclude_assigned_rows_even_if_status_is_pending():
    source = (ROOT / "auth-web" / "lib" / "stdRecommendations.ts").read_text(encoding="utf-8")

    assert source.count(".is('assigned_at', null)") >= 2
    assert source.count(".is('assigned_employee_email', null)") >= 2


def test_std_frontend_does_not_create_local_project_when_claim_fails():
    source = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")
    claim_catch = source.split("console.warn('[claimTopic] server claim failed:'", 1)[1].split("} finally {", 1)[0]

    assert "Fallback to local workspace" not in source
    assert "buildProjectFromSupabaseTopic(targetTopic)" not in claim_catch
    assert "이미 다른 작업자가 선택한 주제입니다" in claim_catch


def test_std_frontend_only_restores_cached_project_for_same_owner():
    source = (ROOT / "auth-web" / "app" / "std" / "page.tsx").read_text(encoding="utf-8")

    assert "const projectMatchesRequester" in source
    assert "projectPayload.project.employee_email" in source
    assert "projectMatchesRequester(parsed, email || user?.email)" in source
    assert "projectMatchesRequester(remembered, activeImpEmail || email || user?.email)" in source
