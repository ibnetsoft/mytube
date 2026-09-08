from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_drive_reconnect_requires_superadmin_and_uses_offline_consent():
    source = (ROOT / 'auth-web' / 'app' / 'api' / 'admin' / 'google-drive' / 'oauth' / 'route.ts').read_text(encoding='utf-8')

    assert 'requireSuperAdmin(req)' in source
    assert "access_type: 'offline'" in source
    assert "prompt: 'consent'" in source
    assert "scope: DRIVE_SCOPE" in source
    assert "include_granted_scopes" not in source


def test_drive_callback_checks_state_and_stores_the_new_refresh_token():
    source = (ROOT / 'auth-web' / 'app' / 'api' / 'admin' / 'google-drive' / 'oauth' / 'callback' / 'route.ts').read_text(encoding='utf-8')

    assert "pendingStates.includes(receivedState)" in source
    assert "new URL('/dashboard', req.url)" in source
    assert "grant_type: 'authorization_code'" in source
    assert "key: 'sys_api_google_drive_refresh_token'" in source


def test_admin_settings_offers_drive_reconnect_instead_of_refresh_token_entry():
    source = (ROOT / 'auth-web' / 'components' / 'DashboardContent.tsx').read_text(encoding='utf-8')

    assert "handleReconnectGoogleDrive" in source
    assert 'Drive 재연결' in source
    assert "{ key: 'google_drive_refresh_token'" not in source
