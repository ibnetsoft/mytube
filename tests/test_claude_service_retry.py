import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

from services.claude_service import ClaudeService


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        self.calls += 1
        return self.responses.pop(0)


class ClaudeServiceRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_transient_server_error(self):
        client = _Client([
            _Response(500, {"error": {"type": "api_error", "message": "Internal server error"}}),
            _Response(200, {
                "content": [{"text": "complete"}],
                "usage": {"input_tokens": 1, "output_tokens": 2},
                "stop_reason": "end_turn",
            }),
        ])
        service = ClaudeService()

        with patch.object(ClaudeService, "api_key", new_callable=PropertyMock, return_value="test-key"), \
             patch("services.claude_service.httpx.AsyncClient", return_value=client), \
             patch("services.claude_service.asyncio.sleep", new_callable=AsyncMock) as sleep, \
             patch("database.add_ai_log"):
            result = await service.generate_text("prompt")

        self.assertEqual(result, "complete")
        self.assertEqual(client.calls, 2)
        sleep.assert_awaited_once_with(2)


if __name__ == "__main__":
    unittest.main()
