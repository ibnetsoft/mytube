
import sqlite3
import json

def update_variable_prompting():
    try:
        conn = sqlite3.connect('data/wingsai.db')
        cursor = conn.cursor()
        
        # 1. Find the target style key
        cursor.execute("SELECT style_key FROM style_presets")
        styles = cursor.fetchall()
        
        target_key = None
        for (key,) in styles:
            if key and '실사' in key:
                target_key = key
                break
        
        if not target_key:
            print("Target style '실사&졸라맨' not found in DB.")
            return

        print(f"Targeting Style Key: {target_key}")

        # 2. Design the New Variable Prompt Template (English for AI)
        new_prompt_value = """**[Background & Atmosphere]**
A highly detailed, cinematic photorealistic shot of ${LOCATION} during ${TIME}, featuring ${WEATHER}. The environment is captured in sharp 8k resolution with cinematic lighting.

**[Characters & Style]**
Integrated into the photorealistic scene are 15-20 distinct simple "stick-figure" cartoon characters with white orb faces and orange jumpsuits. Seamless hybrid of photo background and 2D vector-style characters.

**[Action & Interaction]**
The orange stick-figure characters are ${ACTION} in the scene.

**[Camera & Quality]**
${CAMERA_ANGLE}, cinematic composition, 8k, sharp focus."""

        # 3. Design the Variable Extraction Instruction (Korean for Gemini)
        new_instruction = """
[변수형 프롬프트(Variable Prompting) 가이드]
당신은 이제 대본의 내용을 분석하여 아래의 5가지 핵심 변수를 추출해야 합니다. 
추출된 변수들은 '프롬프트 템플릿'의 빈자리에 자동으로 채워질 것입니다.

[추출해야 할 변수 리스트]
1. ${LOCATION}: 장면이 일어나는 장소 (예: A heavy rain-soaked deck of an oil tanker, A modern street in Seoul)
2. ${TIME}: 시간대 (예: Midnight, Sunset, Bright daylight)
3. ${WEATHER}: 날씨 상태 (예: Heavy rain, Soft fog, Clear blue sky)
4. ${ACTION}: 주황색 졸라맨 캐릭터들이 하고 있는 구체적인 행동 (예: trembling with fear, running in panic, holding protest signs)
5. ${CAMERA_ANGLE}: 연출 의도에 맞는 카메라 구도 (예: High-angle drone shot, Super macro close-up, Handheld shaky cam)

[작성 규칙]
1. 위 5가지 변수는 반드시 '영어(English)' 키워드 형태로 추출하세요.
2. prompt_en을 구성할 때, 시스템이 제공한 'Base Style Prompt'의 템플릿 구조를 그대로 유지하면서 ${LOCATION} 등의 자리만 당신이 추출한 키워드로 교체하여 완성된 문장으로 출력하세요.
3. 캐릭터는 무조건 '주황색 작업복(orange jumpsuits)'을 입은 '졸라맨(stick-figure)'이어야 함을 명심하세요.
"""

        # 4. Update the DB
        cursor.execute("""
            UPDATE style_presets 
            SET prompt_value = ?, gemini_instruction = ?
            WHERE style_key = ?
        """, (new_prompt_value, new_instruction, target_key))
        
        conn.commit()
        conn.close()
        print(f"Successfully updated '{target_key}' to Variable Prompting system!")

    except Exception as e:
        print(f"Update Failed: {e}")

if __name__ == "__main__":
    update_variable_prompting()
