import os
import sys
import asyncio
from unittest.mock import MagicMock, patch

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.services.voice_analyzer import analyze_voice_task

# Mock Supabase
mock_db = {}

def mock_supabase_patch(table, payload, **kwargs):
    vid = kwargs.get('id', '').replace('eq.', '')
    if vid not in mock_db:
        mock_db[vid] = {}
    mock_db[vid].update(payload)
    return {"success": True}

import app.services.voice_analyzer
app.services.voice_analyzer.web_admin_client.supabase_patch = mock_supabase_patch

async def test_analyzer_success():
    voice_id = "test_vid_1"
    mock_db[voice_id] = {"analysis_status": "pending"}
    
    # Mock httpx
    class MockResponse:
        status_code = 200
        content = b"fake audio content"
    
    class MockClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url): return MockResponse()

    # Mock subprocess
    class MockSubprocessResult:
        stdout = "12.34\n"
        
    def mock_subprocess_run(*args, **kwargs):
        return MockSubprocessResult()

    # Mock Gemini
    class MockGeminiFile:
        name = "mock_file"
        
    class MockGeminiResponse:
        text = '{"voice_traits": {"warmth": 80, "authority": 60, "storytelling": 90, "drama": 70, "education": 50, "luxury": 40, "comedy": 30, "cute": 20, "news": 10, "romance": 50}, "language": "ko"}'
        
    class MockGeminiModels:
        def generate_content(self, model, contents): return MockGeminiResponse()
        
    class MockGeminiFiles:
        def upload(self, file): return MockGeminiFile()
        def delete(self, name): pass
        
    class MockGeminiClient:
        def __init__(self, api_key):
            self.models = MockGeminiModels()
            self.files = MockGeminiFiles()

    with patch('httpx.AsyncClient', return_value=MockClient()):
        with patch('subprocess.run', side_effect=mock_subprocess_run):
            with patch('app.services.voice_analyzer.genai.Client', MockGeminiClient):
                await analyze_voice_task(voice_id, "http://fake.url/audio.mp3")
                
    result = mock_db[voice_id]
    assert result["analysis_status"] == "analyzed"
    assert result["sample_duration"] == 12.34
    assert result["sample_language"] == "ko"
    assert "voice_traits" in result
    assert result["voice_traits"]["warmth"] == 80

async def test_analyzer_failure_download():
    voice_id = "test_vid_2"
    mock_db[voice_id] = {"analysis_status": "pending"}
    
    # Mock httpx to fail
    class MockResponse:
        status_code = 404
        content = b""
    
    class MockClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url): return MockResponse()

    with patch('httpx.AsyncClient', return_value=MockClient()):
        await analyze_voice_task(voice_id, "http://fake.url/audio.mp3")
                
    result = mock_db[voice_id]
    assert result["analysis_status"] == "failed"
    assert result["analysis_result"]["stage"] == "download"
    assert result["analysis_result"]["error"] is True

if __name__ == "__main__":
    asyncio.run(test_analyzer_success())
    asyncio.run(test_analyzer_failure_download())
    print("All mock tests passed!")
