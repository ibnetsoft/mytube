from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_topic_visibility_uses_excluded_status_and_superadmin_auth():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "topics-queue" / "visibility" / "route.ts").read_text(encoding="utf-8")

    assert "requireSuperAdmin(req)" in source
    assert "status: hidden ? 'excluded' : restoredStatus" in source
    assert "admin_hidden_previous_status" in source
    assert ".from('topics_queue')" in source
    assert "updated_at" not in source


def test_admin_topic_queue_loads_hidden_rows_for_management():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "topics-queue" / "route.ts").read_text(encoding="utf-8")

    # Production topics_queue has no updated_at column (SQLSTATE 42703).
    projection = source.split("const TOPICS_QUEUE_LIST_SELECT = `", 1)[1].split("`", 1)[0]
    assert "updated_at" not in projection

    assert "['pending', 'assigned', 'excluded']" in source
    assert "topic?.status === 'excluded'" in source


def test_hidden_topic_endpoint_only_returns_admin_hidden_rows():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "topics-queue" / "visibility" / "route.ts").read_text(encoding="utf-8")

    assert "export async function GET" in source
    assert "requireAdmin(req)" in source
    assert ".eq('status', 'excluded')" in source
    assert "topic?.progress_payload?.admin_hidden === true" in source
    assert "topics: hiddenTopics" in source


def test_admin_topic_queue_ui_can_hide_and_restore_topics():
    source = (ROOT / "auth-web" / "components" / "DashboardContent.tsx").read_text(encoding="utf-8")

    assert "handleTopicVisibility" in source
    assert "'/api/admin/topics-queue/visibility'" in source
    assert "{ key: 'hidden', label: '가림' }" in source
    assert "유저웹 가림" in source
    assert "가림 해제" in source
    assert "가림된 주제" in source
    assert "가림주제: {hiddenTopics.length}개" in source
    assert "handleTopicVisibility(topicItem, false)" in source
    assert "admin/topics-queue/visibility" in source
    assert "setHiddenAdminTopics" in source
    assert "String(t.category_id) === String(cat.id)" in source

    preview = source.split("previewTopicItems.map((topicItem, idx)", 1)[1].split("{activeTab === 'topics-queue'", 1)[0]
    edit_index = preview.index("수정")
    hide_index = preview.index("'가림'")
    delete_index = preview.index("삭제")
    assert edit_index < hide_index < delete_index


def test_user_recommendations_only_return_pending_topics():
    source = (ROOT / "auth-web" / "lib" / "stdRecommendations.ts").read_text(encoding="utf-8")

    assert source.count(".eq('status', 'pending')") >= 2


def test_codex_worker_admin_can_bulk_hide_visible_topics_for_repair():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "codex-worker" / "route.ts").read_text(encoding="utf-8")
    page = (ROOT / "auth-web" / "app" / "admin" / "codex-worker" / "page.tsx").read_text(encoding="utf-8")

    assert "hide-visible-for-repair" in source
    assert "repair_status: 'listed'" in source
    assert "status: 'excluded'" in source
    assert ".from('user_topic_recommendations')" in source
    assert ".delete()" in source
    assert "visible_user_topics" in source

    assert "기존 토픽 리페어 목록" in page
    assert "현재 노출 토픽 전체 가림" in page
    assert "'/api/admin/topics-queue/repair'" in page


def test_codex_worker_admin_lists_repair_jobs_separately_from_normal_generation():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "codex-worker" / "route.ts").read_text(encoding="utf-8")

    assert "const CODEX_JOB_TYPE = 'codex_content_generate'" in source
    assert "const REPAIR_JOB_TYPE = 'script_plan_generate'" in source
    assert "isRepairJob" in source
    assert "repair_topics: repairTopics" in source
