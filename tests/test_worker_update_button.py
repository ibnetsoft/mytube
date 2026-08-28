from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_worker_update_button_uses_safe_git_update_route():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")
    git_info_body = source.split("def api_system_git_info(", 1)[1].split("def _perform_safe_git_update", 1)[0]
    git_pull_body = source.split("def api_system_git_pull(", 1)[1].split("# ---------------------------------------------------------------------------", 1)[0]

    assert "return _perform_safe_git_update()" not in git_info_body
    assert "return _perform_safe_git_update()" in git_pull_body
    assert '["stash", "push", "--include-untracked"' in source
    assert '["fetch", "origin", "main"]' in source
    assert '["pull", "--ff-only", "origin", "main"]' in source
    assert "timeout=120" in source
    assert '"dirty_before"' in source
    assert '"stash_created"' in source
    assert '"stash_restored"' in source


def test_worker_update_button_calls_git_pull_api():
    source = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")

    assert "async function updateWorkerCode" in source
    assert "api('POST', '/api/system/git-pull')" in source
