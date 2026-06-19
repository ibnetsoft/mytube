import unittest
from unittest.mock import patch
from unittest.mock import mock_open
import json

from fastapi import BackgroundTasks
from fastapi import UploadFile
import database
from app.routers import projects


class ProjectMusicIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_project_detail_includes_settings_app_mode(self):
        with (
            patch.object(
                projects.db,
                "get_project",
                return_value={"id": 123, "name": "Music Project", "topic": "Cafe Music"},
            ),
            patch.object(
                projects.db,
                "get_project_settings",
                return_value={"app_mode": "longform_music", "title": "Cafe Music", "duration_seconds": 240},
            ),
        ):
            data = await projects.get_project(123, BackgroundTasks())

        self.assertEqual(data["app_mode"], "longform_music")
        self.assertEqual(data["video_title"], "Cafe Music")
        self.assertEqual(data["duration_seconds"], 240)

    async def test_save_music_plan_persists_plan_and_updates_topic(self):
        from app.routers import music

        req = music.MusicSavePlanRequest(
            project_id=321,
            plan={"playlist_title": "Midnight Drive", "tracks": [{"title": "Track 01"}]},
            config={"playlist_title": "Midnight Drive"},
        )

        with (
            patch.object(music.db, "get_project", return_value={"id": 321, "name": "Music Project"}),
            patch.object(music.music_plan_service, "save_plan") as save_plan,
            patch.object(music.db, "update_project") as update_project,
        ):
            data = await music.save_music_plan(req)

        self.assertEqual(data["status"], "ok")
        save_plan.assert_called_once()
        update_project.assert_called_once_with(321, topic="Midnight Drive")

    async def test_generate_music_cover_updates_cover_setting(self):
        from app.routers import image

        req = image.MusicCoverGenerateRequest(
            project_id=9,
            prompt="night drive playlist cover",
            image_type="cover",
            style="cinematic",
            aspect_ratio="16:9",
        )

        with (
            patch.object(image.db, "get_project", return_value={"id": 9, "name": "Night Drive"}),
            patch.object(image, "generate_image", return_value={"status": "ok", "image_url": "/output/night_cover.png"}),
            patch.object(image.db, "update_project_setting") as update_setting,
        ):
            data = await image.generate_music_cover(req)

        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["image_url"], "/output/night_cover.png")
        update_setting.assert_called_once_with(9, "template_image_url", "/output/night_cover.png")

    async def test_get_music_plan_normalizes_track_count_from_saved_config(self):
        from app.routers import music

        saved_plan = {
            "playlist_title": "Cafe Focus",
            "genre": "lofi",
            "mood": "calm",
            "tracks": [
                {"title": "Track 01", "mood": "calm", "prompt": "piano intro", "duration_seconds": 240},
            ],
        }
        settings = {
            "longform_music": json.dumps({"genre": "lofi", "track_count": 2, "playlist_duration_seconds": 480}),
            "longform_music_plan_json": json.dumps(saved_plan),
        }

        with (
            patch.object(music.db, "get_project", return_value={"id": 321, "name": "Cafe Focus", "topic": "Cafe Focus"}),
            patch.object(music.db, "get_project_settings", return_value=settings),
            patch.object(music, "_load_generated_tracks", return_value=[]),
        ):
            data = await music.get_music_plan(321)

        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["plan"]["tracks"]), 2)
        self.assertNotEqual(data["plan"]["tracks"][0]["title"], "Track 01")
        self.assertNotEqual(data["plan"]["tracks"][1]["title"], "Track 02")

    async def test_music_plan_supports_japanese_enka_tags_and_fallback_titles(self):
        from services.music_plan_service import music_plan_service

        plan = {
            "playlist_title": "황혼의 엔카 카페",
            "genre": "japanese_enka",
            "mood": "nostalgic",
            "tracks": [
                {"title": "Track 01", "mood": "nostalgic", "prompt": "Track 01"},
                {"title": "Track 02", "mood": "melancholy", "prompt": ""},
            ],
        }

        normalized = music_plan_service.coerce_tracks(
            plan,
            {"genre": "japanese_enka", "track_count": 2, "playlist_duration_seconds": 360},
        )

        self.assertEqual(len(normalized), 2)
        self.assertIn("Shamisen", music_plan_service.get_style_tags("japanese_enka"))
        self.assertTrue(all(not item["title"].lower().startswith("track ") for item in normalized))
        self.assertIn("Japanese Enka", normalized[0]["prompt"])


class ProjectMusicStatusTest(unittest.TestCase):
    def test_longform_music_project_uses_music_progress_fields(self):
        fake_rows = [
            {
                "id": 77,
                "name": "Lofi Playlist",
                "topic": "Night Drive",
                "project_status": "remote_queued",
                "created_at": "2026-06-18 10:00:00",
                "updated_at": "2026-06-18 12:00:00",
                "video_title": "Late Night Lofi",
                "name_vi": "",
                "topic_vi": "",
                "video_title_vi": "",
                "has_script": 0,
                "has_structure": 0,
                "has_music_plan": 1,
                "has_music_tracks": 1,
                "image_count": 0,
                "has_tts": 0,
                "video_path": "",
                "external_video_path": "",
                "template_image_url": "/static/music_cover.png",
                "thumbnail_url": "",
                "upload_schedule_at": "2026-06-20T09:00:00",
                "is_uploaded": 0,
                "is_published": 0,
                "thumbnail_count": 1,
                "app_mode": "longform_music",
                "description": "Playlist description",
                "employee_email": None,
            }
        ]

        class FakeCursor:
            def execute(self, *_args, **_kwargs):
                return None

            def fetchall(self):
                return fake_rows

        class FakeConn:
            def __init__(self):
                self.row_factory = None

            def cursor(self):
                return FakeCursor()

            def close(self):
                return None

        with patch.object(database, "get_db", return_value=FakeConn()):
            data = database.get_projects_with_status()

        self.assertEqual(len(data), 1)
        progress = data[0]["progress"]
        self.assertTrue(progress["music_plan"])
        self.assertTrue(progress["music_cover"])
        self.assertTrue(progress["music_tracks"])
        self.assertTrue(progress["music_thumbnail"])
        self.assertTrue(progress["music_render"])
        self.assertTrue(progress["music_desc"])
        self.assertTrue(progress["music_publish"])
        self.assertTrue(progress["plan"])
        self.assertTrue(progress["upload"])

    def test_delete_music_track_removes_matching_entry(self):
        from app.routers import music

        tracks = [
            {"index": 0, "title": "Track 01", "file_path": "/output/1/assets/audio/longform_music/tracks/track_00.mp3"},
            {"index": 1, "title": "Track 02", "file_path": "/output/1/assets/audio/longform_music/tracks/track_01.mp3"},
        ]

        async def run():
            req = music.MusicDeleteTrackRequest(project_id=1, index=0)
            with (
                patch.object(music.db, "get_project", return_value={"id": 1}),
                patch.object(music, "_load_generated_tracks", return_value=list(tracks)),
                patch.object(music, "_save_generated_tracks") as save_tracks,
                patch("app.routers.music.os.path.exists", return_value=False),
            ):
                data = await music.delete_music_track(req)
            self.assertEqual(data["status"], "ok")
            self.assertTrue(data["deleted"])
            self.assertEqual(len(data["tracks"]), 1)
            self.assertEqual(data["tracks"][0]["index"], 1)
            save_tracks.assert_called_once()

        import asyncio
        asyncio.run(run())

    def test_music_render_playlist_queues_remote_drive_render(self):
        from app.routers import music
        import io
        import asyncio

        async def run():
            upload = UploadFile(filename="cover.jpg", file=io.BytesIO(b"fake-image"))
            with (
                patch.object(music.db, "get_project", return_value={"id": 1, "name": "Music Project"}),
                patch.object(
                    music.db,
                    "get_project_settings",
                    return_value={
                        "template_image_url": "/output/1/assets/images/longform_music/cover.jpg",
                        "thumbnail_url": "/output/1/assets/images/longform_music/thumbnail.jpg",
                        "title": "Night Drive",
                        "description": "playlist description",
                    },
                ),
                patch.object(music.db, "get_metadata", return_value={"titles": ["Night Drive"], "description": "playlist description"}),
                patch.object(music.db, "update_project") as update_project,
                patch.object(music.db, "update_project_setting") as update_project_setting,
                patch.object(music, "_resolve_track_local_path", return_value="C:\\tracks\\track_01.mp3"),
                patch("app.routers.music.os.makedirs"),
                patch("app.routers.music.os.path.exists", return_value=True),
                patch("app.routers.music.open", mock_open(), create=True),
                patch.object(music, "package_music_project_assets", return_value="C:\\tmp\\music_pkg.zip"),
                patch.object(
                    music.remote_drive_render_service,
                    "enqueue_packaged_project",
                    return_value={"task_id": "task-123", "drive_file": {"id": "drive-456"}},
                ) as enqueue_packaged_project,
            ):
                data = await music.render_music_playlist(
                    project_id=1,
                    playlist_title="Night Drive",
                    image=upload,
                    track_files=["/output/1/assets/audio/longform_music/tracks/track_01.mp3"],
                    track_durations=[180],
                    render_target="drive_api",
                )

            self.assertEqual(data["status"], "queued")
            self.assertEqual(data["task_id"], "task-123")
            update_project.assert_called_once_with(1, status="remote_packaging")
            self.assertTrue(update_project_setting.called)
            enqueue_packaged_project.assert_called_once()

        asyncio.run(run())

    def test_music_render_playlist_requires_thumbnail_and_metadata(self):
        from app.routers import music
        import io
        import asyncio
        from fastapi import HTTPException

        async def run():
            upload = UploadFile(filename="cover.jpg", file=io.BytesIO(b"fake-image"))
            with (
                patch.object(music.db, "get_project", return_value={"id": 1, "name": "Music Project"}),
                patch.object(music.db, "get_project_settings", return_value={"template_image_url": "/output/1/assets/images/longform_music/cover.jpg"}),
                patch.object(music.db, "get_metadata", return_value={}),
                patch.object(music, "_resolve_track_local_path", return_value="C:\\tracks\\track_01.mp3"),
                patch("app.routers.music.os.makedirs"),
                patch("app.routers.music.os.path.exists", return_value=True),
                patch("app.routers.music.open", mock_open(), create=True),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    await music.render_music_playlist(
                        project_id=1,
                        playlist_title="Night Drive",
                        image=upload,
                        track_files=["/output/1/assets/audio/longform_music/tracks/track_01.mp3"],
                        track_durations=[180],
                        render_target="drive_api",
                    )
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Thumbnail image is required", ctx.exception.detail)

        asyncio.run(run())

    def test_music_upload_endpoint_uses_project_publish_service(self):
        from app.routers import video
        import asyncio

        async def run():
            req = video.MusicUploadRequest(
                privacy_status="private",
                publish_at="2026-06-20T00:00:00Z",
                channel_id=7,
            )
            with (
                patch.object(video.db, "get_project", return_value={"id": 1, "name": "Music Project"}),
                patch.object(video.db, "get_project_settings", return_value={"app_mode": "longform_music", "video_path": "/output/rendered.mp4"}),
                patch.object(video.db, "update_project_setting") as update_project_setting,
                patch.object(
                    video,
                    "queue_project_for_admin_publish",
                    return_value={"status": "ok", "queue_status": "pending_review", "url": "https://drive.google.com/file/d/abc123/view"},
                ) as queue_publish,
            ):
                data = await video.upload_music_project_to_youtube(1, req)

            self.assertEqual(data["status"], "ok")
            queue_publish.assert_called_once_with(
                1,
                requested_privacy="private",
                requested_publish_at="2026-06-20T00:00:00Z",
                requested_channel_id=7,
            )
            update_project_setting.assert_called_once_with(1, "upload_schedule_at", "2026-06-20T00:00:00Z")
            self.assertEqual(data["queue_status"], "pending_review")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
