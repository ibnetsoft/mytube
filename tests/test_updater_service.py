import unittest
from unittest.mock import Mock, patch

from services import updater_service as updater_module


class UpdaterServiceTests(unittest.TestCase):
    def test_development_runtime_does_not_offer_an_in_place_update(self):
        service = updater_module.UpdaterService()

        with patch.object(updater_module.sys, "frozen", False, create=True), patch.object(
            updater_module.config, "APP_VERSION", "2.3.39"
        ), patch.object(updater_module.requests, "get") as get:
            result = service.check_for_update()

        self.assertFalse(result["has_update"])
        self.assertFalse(result["can_apply_update"])
        self.assertEqual(result["current_version"], "2.3.39")
        get.assert_not_called()

    def test_packaged_runtime_compares_against_installed_version_record(self):
        service = updater_module.UpdaterService()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "tag_name": "v2.3.40",
            "assets": [
                {
                    "name": "AIRStudio-2.3.40-win-x64.zip",
                    "browser_download_url": "https://example.test/AIRStudio-2.3.40-win-x64.zip",
                    "digest": "sha256:abc123",
                }
            ],
        }

        with patch.object(updater_module.sys, "frozen", True, create=True), patch.object(
            updater_module.config, "APP_VERSION", "2.3.39"
        ), patch.object(updater_module.requests, "get", return_value=response):
            result = service.check_for_update()

        self.assertTrue(result["has_update"])
        self.assertTrue(result["can_apply_update"])
        self.assertEqual(result["current_version"], "2.3.39")
        self.assertEqual(result["latest_version"], "2.3.40")


if __name__ == "__main__":
    unittest.main()
