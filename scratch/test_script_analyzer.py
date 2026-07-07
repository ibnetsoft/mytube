import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.script_analyzer import script_analyzer_service

async def test_analyzer():
    # 1. 한국어 대본, 등장인물 1명
    script_ko_1 = """
    주인공: (화난 목소리로) 도대체 이게 무슨 일이야! 내가 그렇게 말했는데도...
    """
    print("=== Test 1: Korean, 1 Character ===")
    res1 = await script_analyzer_service.analyze_script(script_ko_1)
    print(res1)
    print("\n")

    # 2. 영어 대본, 등장인물 여러 명
    script_en_multi = """
    John: (calmly) We need to defuse this situation right now.
    Sarah: (panicking) But the timer is at 10 seconds! We're all going to die!
    Commander: Hold your positions. I'm sending backup.
    """
    print("=== Test 2: English, Multi Characters ===")
    res2 = await script_analyzer_service.analyze_script(script_en_multi)
    print(res2)
    print("\n")

    # 3. 내레이션 포함
    script_narration = """
    [나레이션] 그날 밤, 숲속은 평소보다 훨씬 고요했다. 바람소리조차 들리지 않았다.
    어린 소년은 조심스럽게 발걸음을 옮겼다.
    소년: 엄마...? 어디 계세요?
    [나레이션] 하지만 메아리만 돌아올 뿐이었다.
    """
    print("=== Test 3: Narration Included ===")
    res3 = await script_analyzer_service.analyze_script(script_narration)
    print(res3)
    print("\n")

    # 4. JSON 파싱 실패 유도 (빈 대본 또는 이상한 텍스트 처리)
    script_empty = "      "
    print("=== Test 4: Empty / Invalid Script ===")
    res4 = await script_analyzer_service.analyze_script(script_empty)
    print(res4)
    print("\n")

if __name__ == "__main__":
    asyncio.run(test_analyzer())
