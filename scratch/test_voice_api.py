import os
import sys

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi.testclient import TestClient
from main import app
from app.routers.admin_voices import VoiceCreatePayload, VoiceUpdatePayload
from app.routers.voices import RecommendRequest

# Initialize test client
client = TestClient(app)

# Note: In a real environment, we would need to mock authentication or bypass `require_superadmin`.
# Since we are just verifying logic, we will mock `require_superadmin` temporarily for testing.
import app.routers.admin_tenant
import app.routers.admin_voices
app.routers.admin_tenant.require_superadmin = lambda: True
app.routers.admin_voices.require_superadmin = lambda: True

def run_tests():
    print("Running AIR-0201 API Tests...\n")
    
    # We will mock _supabase_post, _supabase_get, etc. to not actually hit the real DB, 
    # OR we can hit the real dev DB if it's connected.
    # To be safe and test logic, let's mock the db responses.
    
    mock_db = []
    
    def mock_supabase_post(table, payload):
        import uuid
        payload['id'] = str(uuid.uuid4())
        payload['is_active'] = True
        mock_db.append(payload)
        return payload
        
    def mock_supabase_get(table, **params):
        results = mock_db
        if params.get('id'):
            val = params['id'].replace('eq.', '')
            results = [r for r in results if r['id'] == val]
        if params.get('is_active') == 'eq.true':
            results = [r for r in results if r.get('is_active') == True]
        return results
        
    def mock_supabase_patch(table, payload, **params):
        val = params['id'].replace('eq.', '')
        for r in mock_db:
            if r['id'] == val:
                r.update(payload)
                return [r]
        return []

    import app.routers.admin_voices
    app.routers.admin_voices._supabase_post = mock_supabase_post
    app.routers.admin_voices._supabase_get = mock_supabase_get
    app.routers.admin_voices._supabase_patch = mock_supabase_patch
    
    import app.routers.voices
    from unittest.mock import MagicMock
    # voices.py uses web_admin_client directly, so mock that
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_db
    app.routers.voices.web_admin_client.supabase_get = MagicMock(return_value=mock_response)

    # 1. Voice 생성
    print("1. Testing Voice Create...")
    payload = {
        "provider": "elevenlabs",
        "provider_voice_id": "test_voice_1",
        "voice_name": "Test Rachel",
        "language": "en",
        "gender": "female",
        "age_group": "young_adult",
        "tone": "warm",
        "recommended_genres": ["story", "education"],
        "voice_traits": {"warmth": 92, "storytelling": 98},
        "sample_duration": 10.5,
        "sample_language": "en",
        "sample_hash": "hash_12345"
    }
    resp = client.post("/api/admin/voices", json=payload)
    assert resp.status_code == 200, f"Failed to create: {resp.text}"
    data = resp.json()
    assert data["success"] is True
    voice_id = data["data"]["id"]
    print("   -> Voice created with ID:", voice_id)
    
    # 2. Voice 목록 조회
    print("2. Testing Voice List...")
    resp = client.get("/api/admin/voices")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) == 1
    print("   -> List returned", len(data["data"]), "items.")
    
    # 3. Voice 수정
    print("3. Testing Voice Update...")
    resp = client.patch(f"/api/admin/voices/{voice_id}", json={"voice_name": "Updated Rachel", "analysis_status": "needs_review"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"][0]["voice_name"] == "Updated Rachel"
    assert data["data"][0]["analysis_status"] == "needs_review"
    print("   -> Voice updated successfully.")
    
    # 4. /api/voices/recommend 점수 계산 확인
    print("4. Testing Voice Recommend Logic...")
    # Add another voice
    client.post("/api/admin/voices", json={
        "provider": "elevenlabs",
        "provider_voice_id": "test_voice_2",
        "voice_name": "Test John",
        "language": "ko",
        "gender": "male",
        "age_group": "middle_aged",
        "tone": "professional",
        "recommended_genres": ["documentary"]
    })
    
    # Request recommendation for ko, female
    req_payload = {
        "language": "ko",
        "gender": "female",
        "age_group": "young_adult"
    }
    resp = client.post("/api/voices/recommend", json=req_payload)
    assert resp.status_code == 200
    data = resp.json()
    
    voices = data["voices"]
    print("   -> Recommendations:")
    for v in voices:
        print(f"      - {v['voice_name']} (Score: {v['score']}) - {v['reason']}")
        
    assert voices[0]["voice_name"] == "Test John"
    assert voices[0]["score"] == 40
    assert "language" in voices[0]["matched"]
    assert "gender" in voices[1]["matched"]
    
    # 5. Voice Soft Delete
    print("5. Testing Voice Soft Delete...")
    resp = client.delete(f"/api/admin/voices/{voice_id}")
    assert resp.status_code == 200
    print("   -> Soft delete successful.")
    
    # Test List without inactive
    resp = client.get("/api/admin/voices")
    data = resp.json()
    assert len(data["data"]) == 1 # Only John left
    print("   -> Active list returned 1 item.")
    
    print("\nAll tests passed successfully!")

if __name__ == "__main__":
    run_tests()
