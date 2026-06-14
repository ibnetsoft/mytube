import unittest

from app.modes import is_longform_family, is_longform_music_mode, normalize_app_mode


class AppModeTests(unittest.TestCase):
    def test_longform_music_is_dedicated_longform_family_mode(self):
        self.assertEqual(normalize_app_mode("longform_music"), "longform_music")
        self.assertTrue(is_longform_family("longform_music"))
        self.assertTrue(is_longform_music_mode("longform_music"))
        self.assertFalse(is_longform_music_mode("longform"))
        self.assertFalse(is_longform_music_mode("shorts"))


if __name__ == "__main__":
    unittest.main()
