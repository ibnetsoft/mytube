import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, PropertyMock, patch

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

    def test_update_helper_must_be_ready_before_the_app_can_exit(self):
        service = updater_module.UpdaterService()

        with TemporaryDirectory() as temp_dir:
            ready_path = Path(temp_dir) / "apply_update.ready"
            self.assertFalse(service._wait_for_helper_ready(ready_path, timeout_seconds=0))

            ready_path.write_text("helper-started:1", encoding="ascii")
            self.assertTrue(service._wait_for_helper_ready(ready_path, timeout_seconds=0))

    def test_apply_keeps_the_app_running_when_the_update_helper_does_not_start(self):
        service = updater_module.UpdaterService()

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_dir = root / "app"
            app_dir.mkdir()
            package_path = root / "AIRStudio-update.zip"
            with zipfile.ZipFile(package_path, "w") as package:
                package.writestr("AIRStudio.exe", "placeholder")
                package.writestr("version.json", '{"version":"2.3.42"}')

            service.download_path = package_path
            service.download_progress = 100
            with patch.object(updater_module.sys, "frozen", True, create=True), patch.object(
                updater_module.config, "LOCAL_APP_DATA_DIR", str(root)
            ), patch.object(
                type(service), "_app_dir", new_callable=PropertyMock, return_value=app_dir
            ), patch.object(
                type(service), "_run_schtasks", return_value=(False, "Task Scheduler is unavailable")
            ) as run_schtasks:
                success, error = service.apply_update_and_restart()

        self.assertFalse(success)
        self.assertIn("Unable to schedule", error)
        self.assertFalse(service.is_applying)
        run_schtasks.assert_called_once()

    def test_update_helper_preserves_runtime_environment_for_the_restarted_app(self):
        service = updater_module.UpdaterService()
        captured = {}

        def write_script(content, encoding):
            captured["content"] = content
            captured["encoding"] = encoding

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_dir = root / "app"
            app_dir.mkdir()
            package_path = root / "AIRStudio-update.zip"
            with zipfile.ZipFile(package_path, "w") as package:
                package.writestr("AIRStudio.exe", "placeholder")
                package.writestr("version.json", '{"version":"2.3.42"}')

            service.download_path = package_path
            service.download_progress = 100
            with patch.object(updater_module.sys, "frozen", True, create=True), patch.object(
                updater_module.config, "LOCAL_APP_DATA_DIR", str(root)
            ), patch.object(
                type(service), "_app_dir", new_callable=PropertyMock, return_value=app_dir
            ), patch.object(
                updater_module.Path,
                "write_text",
                autospec=True,
                side_effect=lambda path, content, encoding: write_script(content, encoding),
            ), patch.object(
                updater_module.Path, "unlink", autospec=True
            ), patch.object(
                type(service), "_run_schtasks", side_effect=[(True, ""), (True, "")]
            ), patch.object(
                type(service), "_wait_for_helper_ready", return_value=True
            ), patch.object(updater_module.threading, "Thread"):
                with patch.dict(
                    updater_module.os.environ,
                    {"HOST": "127.0.0.1", "PORT": "18002", "LOCALAPPDATA": "C:/temp/local"},
                    clear=False,
                ):
                    success, error = service.apply_update_and_restart()

        self.assertTrue(success, error)
        self.assertEqual(captured["encoding"], "utf-8-sig")
        self.assertIn("$env:HOST = '127.0.0.1'", captured["content"])
        self.assertIn("$env:PORT = '18002'", captured["content"])
        self.assertIn("$env:LOCALAPPDATA = 'C:/temp/local'", captured["content"])


if __name__ == "__main__":
    unittest.main()
