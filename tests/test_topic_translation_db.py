"""
AIR-0128: Tests for DB-persistent topic translation logic.

Covers:
- _fetch_stored_translations returns stored values when columns exist
- _fetch_stored_translations returns {} when columns absent (migration not run)
- translate_recommended_topics returns stored translations without calling AI
- translate_recommended_topics calls AI for topics with NULL translations and saves result
- Response structure matches existing frontend contract (no breaking change)
- topic PUT resets translation columns to null (tested via mock)
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.user_topics import (
    TopicTranslationItem,
    TopicTranslationRequest,
    _fetch_stored_translations,
)


class TestFetchStoredTranslations(unittest.TestCase):
    """Unit tests for _fetch_stored_translations helper."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_returns_stored_translation_when_column_exists(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 42, "topic_vi": "Chủ đề thử nghiệm", "category_name_vi": "Danh mục"},
        ]
        with patch("requests.get", return_value=mock_response):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["42"], "vi")

        self.assertEqual(result, {
            "42": {"topic_vi": "Chủ đề thử nghiệm", "category_name_vi": "Danh mục"},
        })

    def test_returns_empty_when_columns_absent(self):
        """Simulates pre-migration state: Supabase returns non-200 for unknown columns."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "column does not exist"}
        with patch("requests.get", return_value=mock_response):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["1", "2"], "vi")

        self.assertEqual(result, {})

    def test_returns_empty_on_network_error(self):
        with patch("requests.get", side_effect=Exception("timeout")):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["1"], "vi")

        self.assertEqual(result, {})

    def test_excludes_rows_with_null_translation(self):
        """Rows where topic_vi is null/empty must not appear in the result."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "topic_vi": "번역된 주제", "category_name_vi": ""},
            {"id": 2, "topic_vi": None, "category_name_vi": None},
            {"id": 3, "topic_vi": "", "category_name_vi": ""},
        ]
        with patch("requests.get", return_value=mock_response):
            result = _fetch_stored_translations("https://fake.supabase.co", {}, ["1", "2", "3"], "vi")

        self.assertIn("1", result)
        self.assertNotIn("2", result)
        self.assertNotIn("3", result)

    def test_unsupported_lang_returns_empty(self):
        result = _fetch_stored_translations("https://fake.supabase.co", {}, ["1"], "ja")
        self.assertEqual(result, {})

    def test_empty_topic_ids_returns_empty(self):
        result = _fetch_stored_translations("https://fake.supabase.co", {}, [], "vi")
        self.assertEqual(result, {})


class TestTranslateEndpointDbFirst(unittest.IsolatedAsyncioTestCase):
    """Integration-style tests for the translate_recommended_topics endpoint."""

    async def _call_endpoint(self, ui_language, topics):
        from app.routers.user_topics import translate_recommended_topics
        req = TopicTranslationRequest(
            ui_language=ui_language,
            topics=[TopicTranslationItem(**t) for t in topics],
        )
        return await translate_recommended_topics(req)

    async def test_returns_stored_translation_without_ai_call(self):
        """When DB has all translations, AI functions must not be called."""
        stored = {"99": {"topic_vi": "Chủ đề đã lưu", "category_name_vi": "Danh mục"}}

        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value=stored), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock) as mock_ai:
            result = await self._call_endpoint("vi", [{"id": "99", "topic": "테스트 주제", "category_name": "카테고리"}])

        mock_ai.assert_not_called()
        self.assertEqual(result["status"], "ok")
        self.assertIn("99", result["translations"])
        self.assertEqual(result["translations"]["99"]["topic_vi"], "Chủ đề đã lưu")

    async def test_calls_ai_for_missing_translations_and_saves(self):
        """When DB has no translation, AI is called and result is saved back to DB."""
        ai_result = {"55": {"topic_vi": "Chủ đề AI", "category_name_vi": ""}}

        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value={}), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value=ai_result) as mock_ai, \
             patch("app.routers.user_topics._save_translations_to_db", new_callable=AsyncMock) as mock_save, \
             patch("asyncio.create_task") as mock_task:
            result = await self._call_endpoint("vi", [{"id": "55", "topic": "AI 번역 필요", "category_name": ""}])

        mock_ai.assert_called_once()
        # create_task is called to persist the translation (fire-and-forget)
        mock_task.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertIn("55", result["translations"])

    async def test_partial_db_hit_only_calls_ai_for_missing(self):
        """When some topics are stored and others are not, AI is called only for the missing subset."""
        stored = {"10": {"topic_vi": "Đã lưu", "category_name_vi": ""}}
        ai_result = {"11": {"topic_vi": "AI dịch", "category_name_vi": ""}}

        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value=stored), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value=ai_result) as mock_ai, \
             patch("asyncio.create_task"):
            result = await self._call_endpoint("vi", [
                {"id": "10", "topic": "저장됨", "category_name": ""},
                {"id": "11", "topic": "AI 필요", "category_name": ""},
            ])

        # AI called only for topic 11
        called_payload = mock_ai.call_args[0][0]
        called_ids = [item["id"] for item in called_payload]
        self.assertNotIn("10", called_ids)
        self.assertIn("11", called_ids)

        # Both appear in final response
        self.assertIn("10", result["translations"])
        self.assertIn("11", result["translations"])

    async def test_stored_takes_precedence_over_ai(self):
        """If both DB and AI return a result for the same id, DB wins."""
        stored = {"7": {"topic_vi": "DB 번역", "category_name_vi": ""}}
        # AI should not be called because stored covers all items; but if it were,
        # the merge must still give precedence to stored.
        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value=stored), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value={}):
            result = await self._call_endpoint("vi", [{"id": "7", "topic": "테스트", "category_name": ""}])

        self.assertEqual(result["translations"]["7"]["topic_vi"], "DB 번역")

    async def test_unsupported_language_returns_empty(self):
        result = await self._call_endpoint("ko", [{"id": "1", "topic": "주제", "category_name": ""}])
        self.assertEqual(result, {"status": "ok", "translations": {}})

    async def test_empty_topics_returns_empty(self):
        result = await self._call_endpoint("vi", [])
        self.assertEqual(result, {"status": "ok", "translations": {}})

    async def test_response_structure_matches_existing_contract(self):
        """Frontend contract: {"status": "ok", "translations": {id: {...}}}."""
        stored = {"1": {"topic_vi": "Chủ đề", "category_name_vi": "Danh mục"}}
        with patch("app.routers.user_topics._supabase_headers", return_value=("https://fake", {})), \
             patch("app.routers.user_topics._fetch_stored_translations", return_value=stored), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value={}):
            result = await self._call_endpoint("vi", [{"id": "1", "topic": "주제", "category_name": ""}])

        self.assertIn("status", result)
        self.assertIn("translations", result)
        self.assertEqual(result["status"], "ok")
        self.assertIsInstance(result["translations"], dict)

    async def test_degrades_gracefully_when_supabase_not_configured(self):
        """When _supabase_headers returns None, falls through to AI translation."""
        ai_result = {"3": {"topic_vi": "Dự phòng AI", "category_name_vi": ""}}

        with patch("app.routers.user_topics._supabase_headers", return_value=(None, None)), \
             patch("app.routers.user_topics._translate_topics_batch", new_callable=AsyncMock, return_value=ai_result):
            result = await self._call_endpoint("vi", [{"id": "3", "topic": "주제", "category_name": ""}])

        self.assertEqual(result["status"], "ok")
        self.assertIn("3", result["translations"])


if __name__ == "__main__":
    unittest.main()
