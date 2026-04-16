
import sqlite3

def update_cooking_shorts_style():
    try:
        conn = sqlite3.connect('data/wingsai.db')
        cursor = conn.cursor()
        
        # 1. 요리 관련 스타일 키 찾기 (animal_cooking_shorts 등)
        cursor.execute("SELECT style_key FROM style_presets")
        styles = cursor.fetchall()
        
        target_key = None
        for (key,) in styles:
            if key and 'cooking' in key.lower():
                target_key = key
                break
        
        if not target_key:
            print("Target cooking style not found in DB.")
            return

        print(f"Targeting Style Key: {target_key}")

        # 2. 요리 쇼츠 전용 변수형 프롬프트 템플릿 (익스트림 클로즈업 사양)
        new_prompt_value = """**[Food & Subject]**
Super macro, extreme close-up of ${SUBJECT} being ${ACTION}. The focus is entirely on the textures of the ingredients and the sizzling cooking process. No faces, no human bodies. Only professional chef's hands may be visible interacting with food or tools.

**[Cookware & Atmosphere]**
Inside a professional ${COOKWARE_OR_TOOLS} (e.g., a seasoned flaming wok, a cast iron skillet). High heat, rising steam, splattering oil, and glowing embers. Realistic ${LOCATION} kitchen environment blurred in the background.

**[Style & Lighting]**
Cinematic food cinematography, vibrant and appetizing colors, professional food photography lighting. High-speed shutter feel to capture sharp movement of food.

**[Camera & Quality]**
Top-down macro angle or extremely low-angle close-up, razor-sharp focus on the food, 8k resolution, cinematic composition. NO TEXT."""

        # 3. 요리 쇼츠 전용 지능형 추출 지침
        new_instruction = """
[고출력 요리 쇼츠 전용 변수형 지침]
이 스타일은 '사람'의 존재를 지우고 오직 '음식'과 '박진감 넘치는 조리 과정'에만 모든 시각적 에너지를 쏟아야 합니다.

[핵심 규칙 - 절대 준수]
1. **NO HUMANS (CRITICAL)**: 사람의 얼굴, 상체, 신체 일부는 절대 나오지 않게 하세요. 필요하다면 오직 조리를 수행하는 '전문 셰프의 손(chef's hands)'만 부분적으로 허용됩니다.
2. **SUPER MACRO FOCUS**: 카메라 시선은 반드시 음식에 바짝 다가간 초근접(Macro/Extreme Close-up) 상태여야 합니다. 원거리 샷이나 넓은 주방 샷은 절대 금지됩니다.
3. **DYNAMIC ACTION**: 대본의 내용 중 가장 역동적인 조리 순간(예: 불길이 치솟는 웍질, 소스가 뿌려지는 순간, 고기가 익어가는 소리 등)을 `${ACTION}`으로 추출하세요.

[추출 변수 가이드]
- ${SUBJECT}: 현재 조리 중인 주인공 식재료 (예: sizzling diced pork belly, fresh green vegetables, spicy seafood mix)
- ${ACTION}: 박진감 넘치는 동작 (예: tossing in a flaming wok, stir-frying over high heat, drizzling thick sauce)
- ${COOKWARE_OR_TOOLS}: 조리 도구 (예: seasoned carbon steel wok, heavy iron pan, flaming professional stove)
- ${LOCATION}: 배경 분위기 (예: professional high-heat Asian kitchen, modern dimly lit restaurant kitchen)

[출력 형식]
prompt_en을 작성할 때 위 템플릿의 변수들을 당신이 추출한 영어 키워드로 정확히 교체하여 완성된 문단으로 출력하세요.
끝에 반드시 추가: "no faces, no people, no humans, no text, no words, no letters, no captions, no subtitles, no watermarks, no speech bubbles"
"""

        # 4. DB 업데이트
        cursor.execute("""
            UPDATE style_presets 
            SET prompt_value = ?, gemini_instruction = ?
            WHERE style_key = ?
        """, (new_prompt_value, new_instruction, target_key))
        
        conn.commit()
        conn.close()
        print(f"Successfully specialized '{target_key}' for Extreme Cooking Shorts!")

    except Exception as e:
        print(f"Update Failed: {e}")

if __name__ == "__main__":
    update_cooking_shorts_style()
