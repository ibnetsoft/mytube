import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.script_analyzer import script_analyzer_service

def validate_response(res):
    scenes = res.get('scenes', [])
    chars = res.get('characters', [])
    
    assert res.get('scene_count', 0) == len(scenes), f"Scene count mismatch: {res.get('scene_count')} != {len(scenes)}"
    
    est_dur = res.get('estimated_duration', 0)
    sum_dur = sum(s.get('estimated_seconds', 0) for s in scenes)
    # Allow 10% or fixed margin of error
    assert abs(est_dur - sum_dur) <= max(10, est_dur * 0.2), f"Duration mismatch: {est_dur} != sum({sum_dur})"
    
    char_ids = {c.get('id') for c in chars if c.get('id')}
    for s in scenes:
        spk = s.get('tts_hint', {}).get('speaker_id')
        if spk and spk.lower() != 'narrator':
            assert spk in char_ids, f"Speaker ID {spk} not found in characters"

async def test_analyzer():
    # 1. 한국어 감동 사연 대본 -> scenes 3개 이상
    script_ko_1 = """
    주인공: (울먹이며) 엄마, 저 정말 열심히 살았어요. 그런데 왜 이렇게 힘든 걸까요.
    엄마: (따뜻하게 안아주며) 우리 딸, 괜찮아. 엄마가 항상 네 편이잖아. 잠시 쉬어가도 돼.
    [나레이션] 그날 밤, 나는 엄마의 품에서 어린아이처럼 엉엉 울었다.
    다음 날 아침이 밝았을 때, 세상은 어제와 같았지만 내 마음은 한결 가벼워졌다.
    주인공: (밝은 목소리로) 다녀오겠습니다!
    """
    print("=== Test 1: Korean Emotional Script ===")
    res1 = await script_analyzer_service.analyze_script(script_ko_1)
    print(res1)
    assert res1['language'] == 'ko', "Language should be ko"
    assert len(res1['scenes']) >= 3, "Should extract 3 or more scenes"
    validate_response(res1)
    print("Test 1 PASS\n")

    # 2. 영어 대본, 등장인물 여러 명
    script_en_multi = """
    John: (calmly) We need to defuse this situation right now.
    Sarah: (panicking) But the timer is at 10 seconds! We're all going to die!
    Commander: Hold your positions. I'm sending backup.
    """
    print("=== Test 2: English, Multi Characters ===")
    res2 = await script_analyzer_service.analyze_script(script_en_multi)
    print(res2)
    assert res2['language'] == 'en', "Language should be en"
    validate_response(res2)
    print("Test 2 PASS\n")

    # 3. 빈 대본 또는 이상한 텍스트 처리 (Fallback)
    script_empty = "      "
    print("=== Test 3: Empty / Invalid Script ===")
    res3 = await script_analyzer_service.analyze_script(script_empty)
    print(res3)
    assert res3['scenes'] == [], "Scenes should be empty"
    assert res3['scene_count'] == 0, "Scene count should be 0"
    print("Test 3 PASS\n")

    print("ALL TESTS PASSED")

if __name__ == "__main__":
    asyncio.run(test_analyzer())
