from pathlib import Path


STD_PAGE = Path("auth-web/app/std/page.tsx").read_text(encoding="utf-8")


def test_admin_impersonation_is_preserved_by_shared_refresh_loader():
    loader = STD_PAGE.split("const loadStdData = async", 1)[1].split("useEffect(() =>", 1)[0]

    assert "activeImpersonateEmail" in loader
    assert "headers['x-impersonate-email'] = activeImpersonateEmail" in loader
    assert "withImpersonation('/api/std/me')" in loader
    assert "withImpersonation('/api/std/topics?refresh=1&limit=50')" in loader
    assert "withImpersonation('/api/std/projects')" in loader
    assert "withImpersonation('/api/std/voices')" in loader
