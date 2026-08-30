from pathlib import Path


ADMIN_SETTINGS = Path("auth-web/app/api/admin/settings/global/route.ts").read_text(encoding="utf-8")
DASHBOARD = Path("auth-web/components/DashboardContent.tsx").read_text(encoding="utf-8")
DRIVE_CONFIG = Path("auth-web/lib/googleDriveConfig.ts").read_text(encoding="utf-8")
STD_DRIVE = Path("auth-web/lib/stdGoogleDrive.ts").read_text(encoding="utf-8")
ADMIN_DRIVE = Path("auth-web/lib/googleDrive.ts").read_text(encoding="utf-8")
DESKTOP_BRIDGE = Path("auth-web/app/api/desktop-drive-token/route.ts").read_text(encoding="utf-8")
WORKER_DRIVE = Path("worker/drive_adapter.py").read_text(encoding="utf-8")
WEB_ADMIN_CLIENT = Path("services/web_admin_client.py").read_text(encoding="utf-8")


DRIVE_FIELDS = (
    "google_drive_client_id",
    "google_drive_client_secret",
    "google_drive_refresh_token",
    "google_drive_root_folder_id",
)


def test_admin_exposes_plaintext_google_drive_settings():
    for field in DRIVE_FIELDS:
        assert field in ADMIN_SETTINGS
        assert field in DASHBOARD
    assert "apiSettingsTab === 'drive'" in DASHBOARD
    assert 'type="text"' in DASHBOARD


def test_web_drive_consumers_use_shared_admin_first_config():
    assert "hasAnyAdminCredential" in DRIVE_CONFIG
    assert "drive_admin_credentials_incomplete" in DRIVE_CONFIG
    assert "source: 'admin'" in DRIVE_CONFIG
    assert "source: 'environment'" in DRIVE_CONFIG
    assert "getGoogleDriveAccessToken" in STD_DRIVE
    assert "getGoogleDriveAccessToken" in ADMIN_DRIVE
    assert "getGoogleDriveAccessToken" in DESKTOP_BRIDGE
    assert "process.env.GOOGLE_DRIVE_CLIENT_ID" not in STD_DRIVE
    assert "process.env.GOOGLE_DRIVE_CLIENT_ID" not in ADMIN_DRIVE
    assert "process.env.GOOGLE_DRIVE_CLIENT_ID" not in DESKTOP_BRIDGE


def test_worker_receives_admin_drive_token_and_root_through_bridge():
    assert 'root_folder_id: token.config.rootFolderId || null' in DESKTOP_BRIDGE
    assert "drive_bridge_client.get_root_folder_id()" in WORKER_DRIVE
    assert '"sys_api_google_drive_root_folder_id": "REMOTE_RENDER_DRIVE_FOLDER_ID"' in WEB_ADMIN_CLIENT
    assert 'keys["REMOTE_RENDER_DRIVE_FOLDER_ID"] = drive_root' in WEB_ADMIN_CLIENT
