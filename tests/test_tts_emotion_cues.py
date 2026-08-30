import asyncio

from services import tts_service as tts_module


class _FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "alignment": {
                "characters": [],
                "character_start_times_seconds": [],
                "character_end_times_seconds": [],
            },
            "audio_base64": "",
        }


class _FakeAsyncClient:
    payloads = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.payloads.append(json or {})
        return _FakeResponse()


def test_elevenlabs_recognizes_canonical_worker_emotion_cues(monkeypatch, tmp_path):
    _FakeAsyncClient.payloads = []
    monkeypatch.setattr(tts_module.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")

    service = object.__new__(tts_module.TTSService)
    service.output_dir = str(tmp_path)

    samples = [
        ('(따뜻하게) "정말 고맙습니다."', "ko.mp3"),
        ('(firmly) "Tell me the truth!"', "en.mp3"),
        ('(きっぱりと) 「真実を話してください！」', "ja.mp3"),
    ]
    for text, filename in samples:
        asyncio.run(service.generate_elevenlabs(text, filename=filename))

    assert len(_FakeAsyncClient.payloads) == 3
    assert _FakeAsyncClient.payloads[0]["text"].startswith("In an extremely happy")
    assert _FakeAsyncClient.payloads[1]["text"].startswith("In a deep, serious, and thoughtful tone")
    assert _FakeAsyncClient.payloads[2]["text"].startswith("In a deep, serious, and thoughtful tone")
