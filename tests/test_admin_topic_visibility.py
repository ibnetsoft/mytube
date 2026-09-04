from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_topic_visibility_uses_excluded_status_and_superadmin_auth():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "topics-queue" / "visibility" / "route.ts").read_text(encoding="utf-8")

    assert "requireSuperAdmin(req)" in source
    assert "status: hidden ? 'excluded' : restoredStatus" in source
    assert "admin_hidden_previous_status" in source
    assert ".from('topics_queue')" in source


def test_admin_topic_queue_loads_hidden_rows_for_management():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "topics-queue" / "route.ts").read_text(encoding="utf-8")

    assert "['pending', 'assigned', 'excluded']" in source
    assert "topic?.status === 'excluded'" in source


def test_admin_topic_queue_ui_can_hide_and_restore_topics():
    source = (ROOT / "auth-web" / "components" / "DashboardContent.tsx").read_text(encoding="utf-8")

    assert "handleTopicVisibility" in source
    assert "'/api/admin/topics-queue/visibility'" in source
    assert "{ key: 'hidden', label: '가림' }" in source
    assert "유저웹 가림" in source
    assert "가림 해제" in source


def test_user_recommendations_only_return_pending_topics():
    source = (ROOT / "auth-web" / "lib" / "stdRecommendations.ts").read_text(encoding="utf-8")

    assert source.count(".eq('status', 'pending')") >= 2
