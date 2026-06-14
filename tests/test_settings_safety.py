import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import settings


ROOT = Path(__file__).resolve().parents[1]


class SettingsPermissionTests(unittest.TestCase):
    def test_standard_member_cannot_access_advanced_settings_mutations(self):
        with patch("services.auth_service.auth_service.get_membership", return_value="standard"):
            with self.assertRaises(HTTPException) as raised:
                settings._require_advanced_settings_access()

        self.assertEqual(raised.exception.status_code, 403)

    def test_non_standard_member_can_access_advanced_settings_mutations(self):
        with patch("services.auth_service.auth_service.get_membership", return_value="pro"):
            settings._require_advanced_settings_access()

    def test_standard_advanced_global_setting_payload_is_detected(self):
        payload = settings.GlobalSettings(video_engine="veo")
        sent_advanced = [
            key for key in settings.ADVANCED_GLOBAL_SETTING_FIELDS
            if getattr(payload, key, None) is not None
        ]

        self.assertEqual(sent_advanced, ["video_engine"])


class SettingsTemplateTests(unittest.TestCase):
    def test_settings_page_uses_external_javascript_bundle(self):
        html = (ROOT / "templates" / "pages" / "settings.html").read_text(encoding="utf-8")

        self.assertIn("/static/js/settings_page.js", html)
        self.assertIn("window.SETTINGS_CURRENT_PROJECT_ID", html)

    def test_settings_page_bundle_has_no_jinja_tokens(self):
        js = (ROOT / "static" / "js" / "settings_page.js").read_text(encoding="utf-8")

        self.assertNotIn("{{", js)
        self.assertNotIn("{%", js)
        self.assertNotIn("%}", js)


if __name__ == "__main__":
    unittest.main()
