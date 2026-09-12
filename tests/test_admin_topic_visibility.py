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


def test_codex_worker_center_separates_new_generation_and_hidden_repairs():
    api = (ROOT / "auth-web" / "app" / "api" / "admin" / "codex-worker" / "route.ts").read_text(encoding="utf-8")
    page = (ROOT / "auth-web" / "app" / "admin" / "codex-worker" / "page.tsx").read_text(encoding="utf-8")

    assert "hide-visible-for-repair" in api
    assert "repair_topics: repairTopics" in api
    assert "visible_user_topics: visibleUserTopics" in api
    assert "job.job_type === CODEX_JOB_TYPE ? 'new_generation' : 'repair'" in api
    assert "REPAIR_PIPELINE_JOB_TYPES" in api
    assert "기존 토픽 리페어 목록" in page
    assert "신규 토픽 Codex 생성" in page
    assert "'/api/admin/topics-queue/repair'" in page
    assert "targetMinutes: topic.duration_minutes" in page
    assert "targetSceneCount: topic.scene_count" in page


def test_hidden_repair_topics_can_queue_without_becoming_visible():
    repair = (ROOT / "auth-web" / "app" / "api" / "admin" / "topics-queue" / "repair" / "route.ts").read_text(encoding="utf-8")
    complete = (ROOT / "auth-web" / "app" / "api" / "worker-central" / "jobs" / "[jobId]" / "complete" / "route.ts").read_text(encoding="utf-8")

    assert "const isHiddenRepairTopic" in repair
    assert "topic.status === 'excluded'" in repair
    assert "admin_hidden" in repair
    assert ".contains('payload', { topic_queue_id: topicId, repair_mode: true })" in repair
    assert "previousSceneCount > 0 ? previousSceneCount : 53" in repair
    assert "status: existingProgress.admin_hidden" in complete
    assert "? 'excluded'" in complete
    assert "repair_status: 'completed'" in complete


def test_bulk_hide_is_reversible_and_clears_recommendation_cache():
    source = (ROOT / "auth-web" / "app" / "api" / "admin" / "codex-worker" / "route.ts").read_text(encoding="utf-8")

    assert "requireSuperAdmin(req)" in source
    assert "admin_hidden_previous_status: 'pending'" in source
    assert "repair_status: 'listed'" in source
    assert ".from('user_topic_recommendations')" in source
    assert ".in('topic_queue_id', hiddenIds)" in source
