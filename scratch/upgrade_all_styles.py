
import sqlite3

def upgrade_all_styles_to_variable_prompting():
    try:
        conn = sqlite3.connect('data/wingsai.db')
        cursor = conn.cursor()
        
        # 1. 모든 스타일 키 목록 가져오기
        cursor.execute("SELECT style_key FROM style_presets")
        style_keys = [row[0] for row in cursor.fetchall()]
        
        print(f"Found {len(style_keys)} styles to upgrade.")

        # 2. 공통 변수형 프롬프트 구조 정의 로직
        # 스타일 성격에 따라 4가지 메인 카테고리로 분류하여 템플릿 적용
        
        for key in style_keys:
            # 이미 처리한 스타일은 스킵 (실사&졸라맨, 사물캐릭터는 이전 단계에서 완료)
            if any(k in key for k in ['ǻ&', 'ǻ', '繰ĳ', '사물캐릭터', '실사']):
                print(f"Skipping already upgraded style: {key}")
                continue

            low_key = key.lower()
            
            # --- [A] 실사 계열 (Realistic / Photorealistic) ---
            if 'realistic' in low_key or 'photo' in low_key:
                new_prompt = """**[Subject & Atmosphere]**
A cinematic photorealistic shot of ${SUBJECT} in ${LOCATION}. The lighting is ${LIGHTING_DETAILS} with a ${ATMOSPHERE} mood.

**[Environment & Details]**
Detailed environment featuring ${ENVIRONMENT_DETAILS}. High-end textures and sharp details.

**[Camera & Quality]**
${CAMERA_ANGLE}, shot on 35mm lens, f/1.8, 8k resolution, cinematic color grading, ray-traced shadows."""
                
                new_inst = """[실사 변수형 지침]
대본에서 `${SUBJECT}`(인물/대상), `${LOCATION}`(장소), `${LIGHTING_DETAILS}`(조명), `${ACTION}`(행동) 등을 영어 키워드로 추출하여 템플릿에 끼워 넣으세요. 실사 영화 같은 퀄리티를 유지하세요."""

            # --- [B] 지브리/애니메이션 계열 (Ghibli / Anime / 2D) ---
            elif 'ghibli' in low_key or 'anime' in low_key or '2d' in low_key or 'cartoon' in low_key:
                style_name = "Studio Ghibli" if 'ghibli' in low_key else "High-quality 2D Animation"
                new_prompt = f"""**[Subject & Illustration]**
A beautiful {style_name} style illustration of ${{SUBJECT}}. They are ${{ACTION}} with detailed expressions.

**[Background & Colors]**
A scenic background of ${{LOCATION}} during ${{TIME}}. ${{ARTISTIC_DETAILS}}, vibrant yet soft color palette, hand-painted aesthetic.

**[Composition & Quality]**
${{CAMERA_ANGLE}}, clean linework, cinematic anime composition, 4k, crisp focus."""
                
                new_inst = f"[{style_name} 변수형 지침] 대본의 서정적인 분위기를 포착하여 `${{SUBJECT}}`, `${{LOCATION}}`, `${{ACTION}}`을 추출하세요. 특유의 따뜻한 색채와 작화 스타일이 유지되도록 하세요."

            # --- [C] 동요/키즈 계열 (Nursery Rhyme) ---
            elif 'nursery' in low_key or 'rhyme' in low_key:
                new_prompt = """**[Characters & Fantasy]**
Cute 3D Pixar-style characters of ${SUBJECT} in a magical world. They are ${ACTION} with joyful expressions.

**[Environment & Colors]**
A bright, vibrant environment of ${LOCATION}. Soft volumetric lighting, rounded shapes, playful atmosphere.

**[Quality]**
8k, cinematic 3D render, kid-friendly, no text, no words."""
                
                new_inst = "[동요 변수형 지침] 아이들의 눈높이에 맞는 귀엽고 밝은 요소를 `${SUBJECT}`, `${LOCATION}`, `${ACTION}`으로 추출하세요. 무조건 밝고 행복한 느낌이어야 합니다."

            # --- [D] 요리/특수 계열 (Cooking / Animal) ---
            elif 'cooking' in low_key:
                new_prompt = """**[Food & Subject]**
Super macro close-up of ${SUBJECT} being ${ACTION}. Cinematic textures of ingredients.

**[Kitchen & Lighting]**
${LOCATION} background with professional kitchen lighting. Steams rising, vibrant colors, appetizing atmosphere.

**[Camera]**
Super macro shot, slow motion feel, sharp focus on food, 8k."""
                
                new_inst = "[요리 변수형 지침] 음식의 질감이 극대화되도록 `${SUBJECT}`와 `${ACTION}`(조리 동작)을 추출하세요. 사람이 아닌 '음식'이 주인공입니다."

            # --- [E] 기본 기타 계열 ---
            else:
                new_prompt = """**[Main Subject]**
A detailed depiction of ${SUBJECT} who is ${ACTION}.

**[Scene & Style]**
Set in ${LOCATION} with ${STYLE_SPECIFIC_DETAILS}. The overall mood is ${ATMOSPHERE}.

**[Camera & Quality]**
${CAMERA_ANGLE}, high resolution, cinematic composition, vibrant colors."""
                
                new_inst = "[일반 변수형 지침] 대본의 핵심 요소`${SUBJECT}`, `${LOCATION}`, `${ACTION}` 등을 추출하여 스타일과 조화되게 프롬프트를 완성하세요."

            # DB 업데이트 집행 (공통 규칙 추가)
            final_inst = new_inst + "\n끝에 반드시 추가: \"no text, no words, no letters, no captions, no subtitles, no watermarks, no speech bubbles, no Korean text, no English text, no numbers, no labels\""
            
            cursor.execute("""
                UPDATE style_presets 
                SET prompt_value = ?, gemini_instruction = ?
                WHERE style_key = ?
            """, (new_prompt, final_inst, key))
            print(f"Successfully upgraded: {key}")

        conn.commit()
        conn.close()
        print("All styles have been upgraded to the Variable Prompting system!")

    except Exception as e:
        print(f"Global Upgrade Failed: {e}")

if __name__ == "__main__":
    upgrade_all_styles_to_variable_prompting()
