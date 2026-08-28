from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_worker_completion_mirrors_content_feedback_to_notion():
    source = read("auth-web/app/api/internal/worker/jobs/[jobId]/complete/route.ts")

    assert "syncContentFeedbackToNotion" in source
    assert ".from('content_generation_feedback')" in source
    assert ".select('*')" in source


def test_manual_learning_feedback_mirrors_to_notion():
    source = read("auth-web/app/api/admin/learning/route.ts")

    assert "syncContentFeedbackToNotion" in source
    assert "await syncContentFeedbackToNotion(data || row)" in source


def test_hermes_autopilot_reads_notion_learning_rows():
    source = read("worker/hermes_autopilot.py")
    helper = read("worker/notion_learning.py")

    assert "import notion_learning" in source
    assert "fetch_learning_rows(category_id, category" in source
    assert "NOTION_LEARNING_DATABASE_ID" in helper
    assert "https://api.notion.com/v1/databases/" in helper


def test_worker_settings_can_save_notion_env_values():
    config = read("worker/worker_config.py")
    dashboard = read("worker/dashboard_app.py")

    assert '"notion_api_key": "NOTION_API_KEY"' in config
    assert '"notion_learning_database_id": "NOTION_LEARNING_DATABASE_ID"' in config
    assert "notion-learning-settings-card" in dashboard
    assert "Notion 학습 DB 연동" in dashboard
    assert "Notion 설정 저장" in dashboard
    assert "worker-set-notion-api-key" in dashboard
    assert "worker-set-notion-db-id" in dashboard
    assert "notion_api_key_set" in dashboard
