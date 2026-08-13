from pathlib import Path
import unittest

from config import config


class DesktopUploadStorageTests(unittest.TestCase):
    def test_uploads_use_writable_local_app_storage(self):
        self.assertEqual(Path(config.UPLOADS_DIR).parent, Path(config.LOCAL_APP_DATA_DIR))

    def test_main_never_mounts_or_creates_a_relative_uploads_directory(self):
        source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("config.UPLOADS_DIR", source)
        self.assertNotIn('os.makedirs("uploads"', source)
        self.assertNotIn('StaticFiles(directory="uploads")', source)

    def test_commerce_uploads_share_the_configured_upload_directory(self):
        source = Path("app/routers/commerce.py").read_text(encoding="utf-8")

        self.assertIn("Path(config.UPLOADS_DIR) / \"commerce\"", source)


if __name__ == "__main__":
    unittest.main()
