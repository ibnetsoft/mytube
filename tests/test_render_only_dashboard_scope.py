from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "worker" / "dashboard_app.py").read_text(encoding="utf-8")


def test_render_only_profile_hides_script_tabs_and_blocks_direct_navigation():
    assert 'data-worker-profile="__AIR_WORKER_PROFILE__"' in DASHBOARD
    assert "const SCRIPT_TAB_IDS = new Set([" in DASHBOARD
    assert "panel.hidden = !isTabVisibleForWorkerProfile(tabId, profile);" in DASHBOARD
    assert "if (!isTabVisibleForWorkerProfile(tabId, profile)" in DASHBOARD
    assert ".tab-content[hidden] { display: none !important; }" in DASHBOARD
