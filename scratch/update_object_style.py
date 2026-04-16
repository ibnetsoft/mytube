
import sqlite3

def update_object_character_style():
    try:
        conn = sqlite3.connect('data/wingsai.db')
        cursor = conn.cursor()
        
        # 1. '사물캐릭터' 키 찾기
        cursor.execute("SELECT style_key FROM style_presets")
        styles = cursor.fetchall()
        
        target_key = None
        for (key,) in styles:
            if key and '사물캐릭터' in key:
                target_key = key
                break
        
        if not target_key:
            print("Target style '사물캐릭터' not found in DB.")
            return

        print(f"Targeting Style Key: {target_key}")

        # 2. 새로운 변수형 프롬프트 템플릿 설계
        new_prompt_value = """**[Character Concept]**
An anthropomorphic ${OBJECT} designed as an exaggerated Pixar-style 3D animation character. The ${OBJECT} has a highly detailed, expressive face with a ${EXPRESSION} expression.

**[Style & Anatomy]**
Stylized proportions, vibrant colors, cinematic volumetric lighting. Hand-painted textures, specific surface material of a ${OBJECT}. 
STRICTLY EXACTLY TWO ARMS ONLY per character, STRICTLY EXACTLY TWO HANDS ONLY per character. No extra limbs.

**[Action & Scene]**
The ${OBJECT} character is ${ACTION} in a ${ENVIRONMENT}. 

**[Technical Quality]**
8k resolution, Ray-traced shadows, Sharp focus, cinematic 3D render."""

        # 3. 변수 추출 및 랜덤 방지 지침 설계
        new_instruction = """
[사물캐릭터 변수형 스타일 지침]
당신은 대본을 분석하여 '사물이 살아있는 캐릭터'가 된 장면을 설계해야 합니다.

[핵심 규칙 - 절대 준수]
1. **대본 기반 개체 추출 (CRITICAL)**: 반드시 대본의 맥락상 주인공이 되는 핵심 사물을 `${OBJECT}`로 지정하세요. 대본에 언급되지 않은 사물(예: 토마토, 호박 등)을 임의로 생성하는 것은 금지됩니다.
2. **변수 추출 가이드**:
   - ${OBJECT}: 대본에서 주인공으로 묘사된 사물 (예: A rusty old toaster, A shiny gold coin)
   - ${EXPRESSION}: 캐릭터의 현재 감정 (예: determined, terrified, joyful)
   - ${ACTION}: 캐릭터가 하고 있는 구체적인 동작 (예: running for its life, dancing on the table)
   - ${ENVIRONMENT}: 장면의 배경 공간 (예: a messy attic, a luxury bank vault)

[작성 규칙]
1. 모든 변수는 '영어(English)' 키워드나 구절로 추출하세요.
2. prompt_en을 작성할 때, 위 'Base Style Prompt' 템플릿의 변수들을 당신이 추출한 내용으로 정확히 교체하여 하나의 완성된 묘사 문단으로 출력하세요.
3. 끝에 반드시 추가: "no text, no words, no letters, no captions, no subtitles, no watermarks, no speech bubbles, no Korean text, no English text, no numbers, no labels"
"""

        # 4. DB 업데이트
        cursor.execute("""
            UPDATE style_presets 
            SET prompt_value = ?, gemini_instruction = ?
            WHERE style_key = ?
        """, (new_prompt_value, new_instruction, target_key))
        
        conn.commit()
        conn.close()
        print(f"Successfully upgraded '{target_key}' to Variable Prompting system with strict object logic!")

    except Exception as e:
        print(f"Update Failed: {e}")

if __name__ == "__main__":
    update_object_character_style()
