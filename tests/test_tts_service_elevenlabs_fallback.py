import asyncio
import json

from services.tts_service import TTSService
import services.tts_service as tts_module


class _FakeResponse:
    def __init__(self, status_code: int, *, text: str = "", content: bytes = b"", json_data=None):
        self.status_code = status_code
        self.text = text
        self.content = content
        self._json_data = json_data

    def json(self):
        if self._json_data is not None:
            return self._json_data
        return json.loads(self.text)


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        if not self._responses:
            raise AssertionError(f"Unexpected POST: {url}")
        return self._responses.pop(0)


def test_should_fallback_to_standard_elevenlabs_for_unsupported_timestamp_route():
    assert TTSService._should_fallback_to_standard_elevenlabs(
        400,
        "model is not supported on with-timestamps endpoint",
    )
    assert not TTSService._should_fallback_to_standard_elevenlabs(
        429,
        "rate limit exceeded",
    )


def test_generate_elevenlabs_falls_back_to_standard_mp3(monkeypatch, tmp_path):
    async def run():
        fake_client = _FakeAsyncClient(
            [
                _FakeResponse(400, text="model is not supported on with-timestamps endpoint"),
                _FakeResponse(200, content=b"mp3-bytes"),
            ]
        )

        monkeypatch.setattr(tts_module.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
        monkeypatch.setattr(tts_module, "load_dotenv", lambda *args, **kwargs: None)
        monkeypatch.setattr(tts_module.config, "elevenlabs_api_keys", lambda: ["test-key"], raising=False)

        service = TTSService()
        service.output_dir = str(tmp_path)
        monkeypatch.setattr(service, "_align_with_whisper", lambda *args, **kwargs: [])
        monkeypatch.setattr(service, "_duration_from_audio_file", lambda *_args, **_kwargs: 1.25)

        result = await service.generate_elevenlabs(
            "테스트 문장입니다.",
            voice_id="voice-123",
            filename="sample.mp3",
        )

        assert result["audio_path"].endswith("sample.mp3")
        assert result["duration"] == 1.25
        assert (tmp_path / "sample.mp3").read_bytes() == b"mp3-bytes"
        assert len(fake_client.calls) == 2
        assert fake_client.calls[0]["url"].endswith("/voice-123/with-timestamps")
        assert "output_format=mp3_44100_128" in fake_client.calls[1]["url"]

    asyncio.run(run())
