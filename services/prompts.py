"""
AI 프롬프트 템플릿 관리
"""
import json

class Prompts:
    # --- AutoPilot 관련 프롬프트 ---
    AUTOPILOT_ANALYZE_VIDEO = """
        유튜브 쇼츠 영상(ID: {video_id})을 벤치마킹하여 새로운 영상을 만들려 합니다.
        대중들이 좋아할만한 '반전 매력'이나 '공감 포인트'를 3가지만 분석해서 JSON으로 주세요.
        
        JSON 포맷:
        {{
            "sentiment": "positive",
            "topics": ["topic1", "topic2"],
            "viewer_needs": "viewers want..."
        }}
    """

    AUTOPILOT_GENERATE_SCRIPT = """
        분석 내용: {analysis_json}
        
        위 분석을 바탕으로 1분 이내의 유튜브 쇼츠 대본을 작성해줘.
        - 초반 5초에 강력한 후킹 멘트 필수
        - 독백 또는 나레이션 형식으로 작성 (대화체 절대 금지)
        - 화자는 무조건 딱 1명으로 제한
        - 전체 길이는 300자 내외
        
        **[절대 금지 사항 - TTS 읽기 오류 방지]**
        1. 대화 형식(A:, B: 등 가상 대화) 금지
        2. 괄호와 상황 설명 금지 (예: (음악), (상황) 등 절대 넣지 말 것)
        3. 시간 표시 금지 (예: [0-5초], ** 등 타임스탬프 금지)
        4. 이모티콘 및 기호 금지 (예: 🤣, ✨ 등 특수문자 금지)
        5. 화자(이름) 표시 금지 (예: 나:, 상사: 처럼 누가 말하는지 적지 말 것)
        
        오직 '읽을 대사'만 출력해. 설명 제외.
    """

    # --- Gemini Service 관련 프롬프트 ---
    GEMINI_ANALYZE_COMMENTS = """당신은 유튜브 콘텐츠 분석 전문가입니다.
아래 영상의 댓글{script_indicator}를 분석해주세요.

[영상 제목]
{video_title}
{script_section}
[댓글 목록]
{comments_text}

다음 JSON 형식으로 반환해주세요:
{{
    "sentiment": {{
        "positive": 비율,
        "negative": 비율,
        "neutral": 비율
    }},
    "main_topics": ["주요 토픽 1", "주요 토픽 2", ...],
    "viewer_needs": ["시청자 니즈 1", "시청자 니즈 2", ...],
    "content_suggestions": ["콘텐츠 제안 1", "콘텐츠 제안 2", ...],
    "script_analysis": {{
        "structure": "서론-본론-결론 구조 요약",
        "hooks": "초반 몰입을 유도한 요소 (Hooks)",
        "pacing": "영상 전개 속도 및 톤앤매너",
        "key_message": "영상이 전달하고자 하는 핵심 메시지"
    }},
    "summary": "전체 요약 (2-3문장)"
}}

JSON만 반환하세요."""

    GEMINI_EXTRACT_STRATEGY = """당신은 유튜브 알고리즘과 시청자 심리를 꿰뚫어 보는 세계 최고의 컨설턴트입니다.
제시된 영상 분석 데이터를 바탕으로, 다른 영상에도 범용적으로 적용 가능한 **'일반화된 성공 공식(Strategy Logic)'**을 3~5개 추출하세요.

[분석 데이터]
{analysis_json}

**[지침]**
1. 특정 영상의 내용에 국한되지 않고, '구조', '심리', '데이터' 측면에서 성공 원인을 일반화하세요.
2. 유튜브 알고리즘(노출, 클릭률, 시청 지속 시간)에 어떻게 기여하는지 구체적으로 기술하세요.
3. 결과는 반드시 한국어로 작성하세요.

다음 JSON 리스트 형식으로만 답변하세요:
[
    {{
        "category": "hook/structure/emotion/thumbnail/interaction 중 하나",
        "pattern": "일반화된 패턴 제목 (예: 초반 3초 시각적 반전 후킹)",
        "insight": "성공 원인 상세 (알고리즘 및 심리적 근거)",
        "script_style": "어울리는 스타일 (story/informational/all)"
    }}
]
JSON만 반환하세요."""

    GEMINI_SCRIPT_STRUCTURE = """당신은 세계 최고의 유튜브 콘텐츠 기획자이자 스토리텔러입니다.
당신의 임무는 주어진 **키워드(주제)**를 바탕으로, **분석된 성공 전략**과 **누적된 학습 지식**을 적용하여 폭발적인 조회수를 기록할 대본 기획안을 작성하는 것입니다.

### 1. 주제 (Subject Content) - 반드시 이 내용을 다루어야 함
- **핵심 키워드:** {topic_keyword}
- **추가 요청사항:** {user_notes}

### 2. 스타일 및 구조 지침
{specialized_instruction}
- **목표 길이:** {duration_seconds}초 (최소 {min_sections}개 섹션 필요)
{custom_prompt_section}

{knowledge_instruction}

### 4. 벤치마킹 분석 데이터 (Current Success Strategy) - 형식/기법 참고용
- **분석 데이터:** {success_strategy_json}

### 5. 제약 사항
- **언어:** {target_language_context}
- **콘텐츠 분리(CRITICAL):** 벤치마킹 데이터의 줄거리나 고유명사(인물, 채널명 등)를 절대 복제하지 마십시오.
- **창작성:** 주제 키워드({topic_keyword})를 바탕으로 완전히 새로운 인물과 상황을 창조하십시오.
- **중복 방지:** {history_instruction}
- **[대본 작성 절대 규칙 - 위반 시 실패]**
  * 대화체(다중 화자 간의 대화) 금지 -> 반드시 독백이나 나레이션 형식으로 작성
  * 화자는 무조건 딱 1명(성우 1인)으로 제한
  * 괄호와 지문 포함 금지 (예: (배경음악), (웃으며) 등 절대 금지)
  * [0-5초] 같은 시간대/타임스탬프 표시 절대 금지
  * 이모티콘(🤣, ✨ 등) 및 별표(**) 같은 꾸밈 기호 절대 금지
  * "나:", "상사:" 처럼 화자를 구분하는 이름과 콜론 표시 절대 금지
  * 오직 성우가 소리 내어 읽을 '텍스트'만 작성하십시오.
---
다음 JSON 형식으로 기획안을 작성해주세요:
{{
    "hook": "강렬한 멘트 (분석된 기법 적용)",
    "sections": [
        {{
            "title": "섹션 제목",
            "key_points": ["상세 묘사 1", "상세 묘사 2"]
        }}
    ],
    "cta": "구독과 좋아요 멘트",
    "style": "영상 분위기",
    "duration": {duration_seconds}
}}
JSON만 반환하세요."""

    GEMINI_TRENDING_KEYWORDS = """
        Act as a Local Trend Analyst and YouTube SEO Expert for the specific region: {lang_name}.
        
        **OBJECTIVE:**
        Generate a list of 20-30 CURRENT trending search keywords/topics on YouTube specifically for:
        - Region/Language: {lang_name}
        - Time Period: {period_text}
        - Target Age Group: {age_text}

        **STRICT LANGUAGE RULES:**
        1. **"keyword"**: MUST be in the target language ({language}). NOT English (unless it's an English region), NOT Korean.
           - If target is Japanese (ja), keyword MUST be in Japanese (Kanji/Kana).
           - If target is Spanish (es), keyword MUST be in Spanish.
        2. **"translation"**: MUST be the meaning in KOREAN (Hangul).

        **DISTRIBUTION RULES:**
        - Assign a 'volume' score (1-100) using a Power Law distribution.
        - 1-2 keywords: 95-100 (Viral)
        - 3-5 keywords: 70-90 (High)
        - Rest: 20-60 (Moderate)

        **OUTPUT FORMAT (JSON List):**
        [
            {{"keyword": "Keyword in Target Language", "translation": "한국어 뜻 설명", "volume": 98, "category": "Gaming"}},
            ...
        ]

        **EXAMPLES:**
        - If lang=ja: {{"keyword": "猫", "translation": "고양이", "volume": 85, "category": "Pets"}}
        - If lang=es: {{"keyword": "Fútbol", "translation": "축구", "volume": 92, "category": "Sports"}}
        - If lang=en: {{"keyword": "Super Bowl", "translation": "슈퍼볼", "volume": 99, "category": "Sports"}}
        
        RETURN ONLY THE JSON LIST. NO MARKDOWN.
    """

    GEMINI_CHARACTER_PROMPTS = """당신은 영상 캐릭터 디자인 전문가입니다.
아래 대본을 분석하여 등장인물(캐릭터)을 추출하고, 각 캐릭터별로 이미지 생성에 사용할 수 있는 상세한 외형 프롬프트를 작성해주세요.

[대본]
{script}

**분석 지침:**
1. 대본에 언급되거나 암시된 모든 등장인물을 식별하세요.
2. 각 캐릭터의 역할(주인공/조연/배경인물)을 파악하세요.
3. 대본의 맥락에서 유추할 수 있는 외형적 특징을 상세히 묘사하세요.
4. 이미지 생성 AI가 이해할 수 있는 구체적인 영어 프롬프트를 작성하세요.

**외형 묘사 포함 요소:**
- 성별, 예상 연령대
- 얼굴 특징 (이목구비, 표정)
- 헤어스타일 및 색상
- 체형
- 의상 및 액세서리
- 전체적인 분위기/인상

다음 JSON 형식으로 출력해주세요:
{{
    "characters": [
        {{
            "name": "캐릭터 이름 또는 역할",
            "role": "주인공/조연/배경인물",
            "description_ko": "외형 묘사 (한글, 2-3문장)",
            "prompt_en": "Detailed English prompt for image generation, including gender, age, facial features, hairstyle, clothing, expression, atmosphere. Use comma-separated descriptors suitable for AI image generation."
        }}
    ]
}}

- 최대 5명의 주요 캐릭터만 추출하세요.
- prompt_en은 영어로, 이미지 생성 AI에 바로 사용할 수 있는 형식으로 작성하세요.
- JSON만 반환하세요."""

    GEMINI_IMAGE_PROMPTS = """당신은 유튜브 영상 연출 전문가입니다.
아래 대본을 **의미적 장면(Semantic Scene)** 단위로 분할해주세요.

[핵심 원칙]
1. **의미 기반 분할**: 주제, 화자, 분위기, 시공간이 바뀌는 지점에서 장면을 나눕니다.
2. **시간 추정**: 각 장면의 대사 길이를 기준으로 예상 음성 시간을 계산합니다. (한글 약 6자/초)
3. **페이싱 가이드**:
   - 한 장면이 20초 이상이면 시각적으로 지루할 수 있으므로, 이미지 변화가 필요한 서브 포인트를 구분해주세요.
   - 한 장면이 5초 미만이면 인접 장면과 병합을 검토하세요.
4. **목표**: 대본의 흐름에 맞으면서도 시각적 몰입감을 유지하는 {num_scenes}개 내외의 장면

[대본]
{script}

{style_instruction}
{limit_instruction}

다음 JSON 형식으로 출력해주세요:
{{
    "scenes": [
        {{
            "scene_number": 1,
            "scene_title": "장면 요약 (짧은 제목, 예: '주인공의 등장')",
            "scene_text": "해당 장면에서 나오는 대본의 전체 텍스트",
            "script_start": "대본의 첫 어절 (예: '옛날')",
            "script_end": "대본의 마지막 어절 (예: '있었습니다')",
            "estimated_seconds": 15,
            "prompt_ko": "이미지 묘사 (한글)",
            "prompt_en": "{style_prefix}, (영어 묘사)"
        }},
        ...
    ]
}}

- estimated_seconds: 해당 장면의 scene_text를 읽는 데 걸리는 예상 시간 (초)
- 이미지는 16:9 비율(가로형)에 적합해야 합니다.
- 텍스트가 없는 이미지를 묘사해주세요.
- JSON만 반환하세요.
"""

    GEMINI_SUCCESS_ANALYSIS = """당신은 유튜브 콘텐츠 및 바이럴 마케팅 전문가입니다.
제시된 유튜브 영상 정보를 바탕으로, 이 영상이 성공(높은 조회수)한 원인을 분석하고, 이를 벤치마킹한 새로운 콘텐츠를 기획해주세요.

[분석 대상 영상]
- 제목: {title}
- 채널: {channel}
- 조회수: {views}
- 좋아요: {likes}
- 시청자 니즈(댓글 분석 추정): {top_comment}

[요청 사항]
1. **성공 요인 분석 (Success Factor)**: 이 영상이 왜 사람들의 이목을 끌었는지, 제목/썸네일/소재 측면에서 1문장으로 핵심을 뚫어주세요.
2. **벤치마킹 제목 (Pattern Title)**: 원본의 성공 패턴(어그로 포인트)을 유지하되, 약간 다른 각도로 비틀어 새로운 제목을 창작하세요. (너무 똑같으면 안됨)
3. **시놉시스 (Synopsis)**: 해당 제목으로 영상을 만든다면 어떤 내용으로 구성해야 할지 2-3문장으로 요약하세요.

다음 JSON 형식으로만 응답하세요:
{{
    "original_title": "{title}",
    "success_factor": "분석 내용",
    "benchmarked_title": "제안 제목",
    "synopsis": "기획 요약"
}}
JSON만 반환하세요."""

    GEMINI_THUMBNAIL_HOOK_TEXT = """당신은 유튜브 썸네일 카피라이팅 전문가입니다.
아래 영상 대본을 분석하여 클릭률을 극대화하는 썸네일 문구를 생성해주세요.

[영상 대본]
{script}

[스타일 가이드]
- 썸네일 스타일: {thumbnail_style}
- 이미지 스타일: {image_style}
- 타겟 언어: {target_language}

[문구 생성 원칙]
1. **후킹 (Hook)**: 호기심을 자극하는 질문이나 충격적인 진술
2. **간결성**: 3-7단어 (한글 기준 10-20자)
3. **감정 유발**: 놀람, 궁금증, 공감 중 하나 이상
4. **가독성**: 큰 글씨로 읽기 쉬운 단어 선택
5. **스타일 매칭**: 
   - face/dramatic: 감정적, 충격적 ("믿을 수 없는 진실", "충격적인 반전")
   - text/minimal: 정보성, 명확한 ("TOP 5", "핵심 정리")
   - mystery: 질문형, 미스터리 ("진짜 이유는?", "숨겨진 비밀")
   - contrast: 대비, 변화 ("Before vs After", "과거 vs 현재")
   - wimpy: 유머러스, 일상적, 일기 형식 ("나의 처절한 실패기", "절대 하면 안되는 일")

[출력 형식]
JSON 형식으로 5개의 후보 문구를 생성하세요:
{{
    "texts": [
        "후보 문구 1 (가장 강력한 후킹)",
        "후보 문구 2 (감정 유발)",
        "후보 문구 3 (질문형)",
        "후보 문구 4 (숫자/리스트형)",
        "후보 문구 5 (대비/반전형)"
    ],
    "reasoning": "선택 이유 (1-2문장)"
}}

**중요**: 대본의 핵심 메시지를 왜곡하지 말고, 클릭베이트가 아닌 진정성 있는 후킹을 만드세요.
JSON만 반환하세요."""

    THUMBNAIL_IDEA_PROMPT = """
        Topic: {topic}
        Script Summary: {script_summary}
        
        Suggest a high Click-Through-Rate (CTR) Thumbnail Plan.
        JSON Output:
        {
            "hook_text": "Short shocking text (max 5 words)",
            "image_prompt": "Visual description for AI image generator (English, detailed, 16:9)"
        }
    """

    AUTOPILOT_GENERATE_METADATA = """
        당신은 유튜브 SEO 및 마케팅 전문가입니다.
        다음 영상 대본을 바탕으로 클릭률(CTR)과 검색 최적화(SEO)가 뛰어난 제목, 영상 설명, 태그를 생성해주세요.

        [영상 대본]
        {script_text}

        [요구사항]
        1. 제목: 호기심을 유발하고 클릭을 부르는 강렬한 제목 (50자 이내)
        2. 설명: 영상의 내용을 요약하고 관련 키워드를 자연스럽게 포함 (300자 내외). 해시태그 3개 포함.
        3. 태그: 연관도가 높은 검색 키워드 10개 내외 (배열 형식)

        반드시 다음 JSON 형식으로만 반환하세요:
        {{
            "title": "여기에 제목",
            "description": "여기에 설명",
            "tags": ["태그1", "태그2", ...]
        }}
    """

prompts = Prompts()
