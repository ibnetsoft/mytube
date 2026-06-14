import asyncio
import sys
import json
from services.gemini_service import gemini_service

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("Testing translation with gemini-2.5-flash...")
    subtitles = [
        {"text": "뼈대 깊은 가부장적인 집안에서 태어나,"},
        {"text": "평생을 억척스럽게 살아온 시어머니의 삶은"},
        {"text": "그 자체로 단단한 굳은살이었습니다."}
    ]
    texts = [sub["text"] for sub in subtitles]
    
    prompt = f"""You are a professional translator. Translate the following list of video subtitles (in Korean/English/Japanese) into Vietnamese.
Maintain the exact same number of items and order.
Return the result strictly as a JSON list of strings.

Subtitles to translate:
{json.dumps(texts, ensure_ascii=False)}
"""
    try:
        import time
        t0 = time.time()
        res_text = await gemini_service.generate_text(
            prompt, 
            temperature=0.3, 
            project_id=190, 
            task_type="translation", 
            model="gemini-2.5-flash"
        )
        t1 = time.time()
        print(f"Time taken: {t1-t0:.2f}s")
        print("Response:", res_text)
    except Exception as e:
        print("Error:", e)

asyncio.run(main())
