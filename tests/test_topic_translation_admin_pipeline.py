"""
AIR-0129: Tests for admin auto-translation pipeline and translation_status state machine.

Covers:
- User App reads DB translations when admin pipeline has completed (translation_status='completed')
- User App falls back to AI when pipeline is pending/failed (columns are NULL)
- _fetch_stored_translations ignores admin-only columns (translated_at, translation_status)
- translation_status and translated_at do NOT appear in the User App response
- Partial translation (only some languages completed) handled correctly
- AI fallback fires and saves when pipeline has not yet run for a topic
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.user_topics import (
    TopicTranslationItem,
    TopicTranslationRequest,
    _fetch_stored_translations,
)


class TestFetchStoredTranslationsIgnoresAdminColumns(unittest.TestCase):
    """
    _fetch_stored_translations should work correctly even when the Supabase
    response includes AIR-0129 admin columns (translated_at, translation_status).
    The function only reads topic_vi/en/th and category_name_vi/en/th.
    """

    def test_ignores_translated_at_and_translation_status_columns(self):
        """Admin columns included in Supabase response must not appear in the result."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 10,
                "topic_vi": "Chủ đề đã dịch",
                "category_name_vi": "Danh mục",
                "translated_at": "2026-07-04T12:00:00+00:00",  # admin column
                "translation_status": "completed",              # admin column
            }
        ]
        with patch("requests.get", return_value=mock_response):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["10"], "vi")

        self.assertIn("10", result)
        self.assertIn("topic_vi", result["10"])
        self.assertNotIn("translated_at", result["10"])
        self.assertNotIn("translation_status", result["10"])

    def test_completed_status_with_filled_columns_returns_translation(self):
        """
        Simulates: admin pipeline completed, all columns filled.
        User App must use DB value — AI must not be called.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 20,
                "topic_vi": "Chủ đề hoàn thành",
                "category_name_vi": "Danh mục lịch sử",
                "translation_status": "completed",
            }
        ]
        with patch("requests.get", return_value=mock_response):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["20"], "vi")

        self.assertEqual(result["20"]["topic_vi"], "Chủ đề hoàn thành")
        self.assertEqual(result["20"]["category_name_vi"], "Danh mục lịch sử")

    def test_pending_status_with_null_columns_returns_empty(self):
        """
        Simulates: admin pipeline is pending (background task not yet run).
        Columns are NULL → _fetch_stored_translations returns {} for that topic.
        User App must fall back to AI.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 30,
                "topic_vi": None,
                "category_name_vi": None,
                "translation_status": "pending",
            }
        ]
        with patch("requests.get", return_value=mock_response):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["30"], "vi")

        self.assertNotIn("30", result)

    def test_failed_status_with_null_columns_returns_empty(self):
        """
        Simulates: admin pipeline failed (Gemini error).
        Columns are NULL → _fetch_stored_translations returns {} for that topic.
        User App must fall back to AI.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 40,
                "topic_vi": None,
                "category_name_vi": None,
                "translation_status": "failed",
            }
        ]
        with patch("requests.get", return_value=mock_response):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["40"], "vi")

        self.assertNotIn("40", result)


class TestTranslateEndpointWithTranslationStatus(unittest.IsolatedAsyncioTestCase):
    """
    Integration-style tests for translate_recommended_topics when topics_queue
    contains the AIR-0129 translation_status column.
    """

    async def _call_endpoint(self, ui_language, topics):
        from app.routers.user_topics import translate_recommended_topics
        req = TopicTranslationRequest(
            ui_language=ui_language,
            topics=[TopicTranslationItem(**t) for t in topics],
        )
        return await translate_recommended_topics(req)

    async def test_completed_pipeline_serves_from_db_no_ai(self):
        """
        After admin pipeline completes, User App must serve all three languages
        from DB without calling AI.
        """
        stored_en = {
            "50": {"topic_en": "Test Topic in English", "category_name_en": "History"}
        }
        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value=stored_en), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock) as mock_ai:
            result = await self._call_endpoint("en", [{"id": "50", "topic": "테스트", "category_name": "역사"}])

        mock_ai.assert_not_called()
        self.assertEqual(result["status"], "ok")
        self.assertIn("50", result["translations"])
        self.assertEqual(result["translations"]["50"]["topic_en"], "Test Topic in English")

    async def test_pending_pipeline_uses_ai_fallback(self):
        """
        When pipeline is pending (columns NULL), AI fallback is triggered
        and save-back task is scheduled.
        """
        ai_result = {"60": {"topic_vi": "Kết quả AI", "category_name_vi": ""}}

        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value={}), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value=ai_result) as mock_ai, \
             patch("asyncio.create_task") as mock_task:
            result = await self._call_endpoint("vi", [{"id": "60", "topic": "미번역", "category_name": ""}])

        mock_ai.assert_called_once()
        mock_task.assert_called_once()
        self.assertIn("60", result["translations"])

    async def test_failed_pipeline_uses_ai_fallback(self):
        """
        When pipeline failed (columns NULL), AI fallback is triggered.
        """
        ai_result = {"70": {"topic_th": "หัวข้อ AI", "category_name_th": ""}}

        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value={}), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value=ai_result) as mock_ai, \
             patch("asyncio.create_task"):
            result = await self._call_endpoint("th", [{"id": "70", "topic": "미번역", "category_name": ""}])

        mock_ai.assert_called_once()
        self.assertIn("70", result["translations"])

    async def test_mixed_completed_and_pending_topics(self):
        """
        Some topics have admin pipeline completed; others are still pending.
        DB is used for completed topics; AI fires only for pending (NULL) topics.
        """
        stored_vi = {
            "80": {"topic_vi": "Chủ đề đã lưu", "category_name_vi": "Danh mục"}
        }
        ai_result = {"81": {"topic_vi": "AI dịch", "category_name_vi": ""}}

        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value=stored_vi), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value=ai_result) as mock_ai, \
             patch("asyncio.create_task"):
            result = await self._call_endpoint("vi", [
                {"id": "80", "topic": "저장됨", "category_name": ""},
                {"id": "81", "topic": "미번역", "category_name": ""},
            ])

        # AI called only for the pending topic (81)
        called_payload = mock_ai.call_args[0][0]
        called_ids = [item["id"] for item in called_payload]
        self.assertNotIn("80", called_ids)
        self.assertIn("81", called_ids)

        # Both topics appear in response
        self.assertIn("80", result["translations"])
        self.assertIn("81", result["translations"])

    async def test_translation_status_not_in_response(self):
        """
        translation_status and translated_at must never appear in the
        User App response (they are admin-only columns).
        """
        stored = {"90": {"topic_vi": "Chủ đề", "category_name_vi": "DM"}}

        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value=stored), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value={}):
            result = await self._call_endpoint("vi", [{"id": "90", "topic": "주제", "category_name": ""}])

        row = result["translations"].get("90", {})
        self.assertNotIn("translation_status", row)
        self.assertNotIn("translated_at", row)

    async def test_all_three_languages_served_from_db_after_pipeline(self):
        """
        After admin pipeline, all three languages (vi, en, th) are available from DB.
        Each language request is served from DB without AI.
        """
        topic_id = "100"
        base_topic = {"id": topic_id, "topic": "조선시대 비화", "category_name": "역사"}

        for lang_code, key, value in [
            ("vi", "topic_vi", "Câu chuyện bí ẩn"),
            ("en", "topic_en", "The Hidden Story"),
            ("th", "topic_th", "เรื่องราวที่ซ่อนอยู่"),
        ]:
            stored = {topic_id: {f"topic_{lang_code}": value, f"category_name_{lang_code}": ""}}
            with self.subTest(lang=lang_code), \
                 patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
                 patch("app.routers.user_topics._fetch_stored_translations", return_value=stored), \
                 patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock) as mock_ai:
                result = await self._call_endpoint(lang_code, [base_topic])

            mock_ai.assert_not_called()
            self.assertEqual(result["translations"][topic_id][key], value)


if __name__ == "__main__":
    unittest.main()
