import os
import tempfile
import unittest
from unittest.mock import patch

from app.routers import music


class MusicPersistenceTest(unittest.TestCase):
    def test_empty_saved_tracks_falls_back_to_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            track_dir = os.path.join(tmp, "123", "assets", "audio", "longform_music", "tracks")
            os.makedirs(track_dir, exist_ok=True)
            with open(os.path.join(track_dir, "track_00_1000.mp3"), "wb") as f:
                f.write(b"audio")

            original_output_dir = music.config.OUTPUT_DIR
            music.config.OUTPUT_DIR = tmp
            try:
                with patch.object(
                    music.db,
                    "get_project_settings",
                    return_value={"longform_music_generated_tracks_json": "[]"},
                ):
                    tracks = music._load_generated_tracks(123)
            finally:
                music.config.OUTPUT_DIR = original_output_dir

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["status"], "done")
        self.assertEqual(tracks[0]["file_path"], "/output/123/assets/audio/longform_music/tracks/track_00_1000.mp3")

    def test_saved_track_metadata_is_merged_with_generated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            track_dir = os.path.join(tmp, "123", "assets", "audio", "longform_music", "tracks")
            os.makedirs(track_dir, exist_ok=True)
            with open(os.path.join(track_dir, "track_00_1000.mp3"), "wb") as f:
                f.write(b"audio")

            original_output_dir = music.config.OUTPUT_DIR
            music.config.OUTPUT_DIR = tmp
            try:
                with patch.object(
                    music.db,
                    "get_project_settings",
                    return_value={
                        "longform_music_generated_tracks_json": (
                            '[{"index": 0, "title": "Four Minute Track", "prompt": "calm piano", "status": "pending"}]'
                        )
                    },
                ):
                    tracks = music._load_generated_tracks(123)
            finally:
                music.config.OUTPUT_DIR = original_output_dir

        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0]["title"], "Four Minute Track")
        self.assertEqual(tracks[0]["prompt"], "calm piano")
        self.assertEqual(tracks[0]["status"], "done")
        self.assertEqual(tracks[0]["file_path"], "/output/123/assets/audio/longform_music/tracks/track_00_1000.mp3")


if __name__ == "__main__":
    unittest.main()
