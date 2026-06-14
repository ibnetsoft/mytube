"""
Supabase style_presets 테이블에 대본 스타일 프리셋을 일괄 삽입
"""
import os, sys, requests, urllib3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from dotenv import load_dotenv
load_dotenv()

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Supabase credentials not found")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

SCRIPT_STYLES = [
    {
        "preset_type": "script",
        "key_code": "default",
        "display_name_ko": "기본 설정 (자연스럽고 선명한 스타일)",
        "display_name_vi": "Cài đặt cơ bản (Phong cách tự nhiên, sắc nét)",
        "prompt_template": "[자연스럽고 선명한 색감], [깨끗하고 투명한 화질], [사실적인 디테일], [풍부한 질감], [자연광], [편안하고 밝은 분위기], [영화 같은 영상미]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "news",
        "display_name_ko": "뉴스 보도 (News Delivery)",
        "display_name_vi": "Bản tin tức (News Delivery)",
        "prompt_template": "[뉴스 앵커 톤의 차분한 목소리], [정확한 발음], [또렷한 딕션], [간결하고 명확한 문장 구성], [전문적인 정보 전달], [신뢰감 있는 분위기], [앵커 스튜디오 배경]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "old_story",
        "display_name_ko": "옛날 이야기 (Old Story)",
        "display_name_vi": "Chuyện ngày xưa (Old Story)",
        "prompt_template": "[할머니가 들려주시는 듯한 따뜻하고 정겨운 목소리], [구수한 입담], [재미있는 묘사], [상상력을 자극하는 이야기], [과거의 추억을 떠올리게 하는 분위기], [옛날 소품과 배경]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "senior_story",
        "display_name_ko": "시니어 사연 (Senior Story)",
        "display_name_vi": "Câu chuyện người cao tuổi (Senior Story)",
        "prompt_template": "[지나온 삶을 되돌아보는 차분하고 깊이 있는 목소리], [풍부한 경험담], [감동과 교훈이 있는 이야기], [잔잔한 분위기], [삶의 지혜와 따뜻함], [시니어의 관점에서 본 세상]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "bgm_focus",
        "display_name_ko": "배경음악 중심 (BGM Focus)",
        "display_name_vi": "Trung tâm nhạc nền (BGM Focus)",
        "prompt_template": "[배경음악에 맞춰 변하는 영상 연출], [음악의 리듬과 감정을 시각적으로 표현], [다채로운 영상 효과], [음악과 영상의 완벽한 조화], [예술적인 감각]",
        "gemini_instruction": ""
    },
    # 시대별 영화 스타일
    {
        "preset_type": "script",
        "key_code": "classic_50s",
        "display_name_ko": "50년대 클래식 영화 (테크니컬러, 부드러운 조명)",
        "display_name_vi": "Phim cổ điển thập niên 50 (Technicolor, ánh sáng mềm)",
        "prompt_template": "[테크니컬러의 풍부하고 선명한 색감], [부드러운 조명], [클래식한 영화 분위기], [우아한 의상과 헤어스타일], [고전적인 카메라 앵글], [화려하고 낭만적인 분위기]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "joseon_drama",
        "display_name_ko": "조선시대 사극 (전통 건축/의복, 자연광)",
        "display_name_vi": "Phim cổ trang Joseon (kiến trúc/trang phục truyền thống, ánh sáng tự nhiên)",
        "prompt_template": "[조선시대 전통 건축과 의복], [자연광을 활용한 고즈넉한 분위기], [전통적인 한국의 아름다움], [역사적인 배경], [한옥과 궁궐 배경], [사극 영화 같은 영상미]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "north_korea_drama",
        "display_name_ko": "북한 드라마 (빈티지 영화, 강렬한 색감)",
        "display_name_vi": "Phim Bắc Hàn (phim vintage, màu sắc mạnh mẽ)",
        "prompt_template": "[빈티지 영화의 거칠고 투박한 화질], [강렬하고 선명한 색감], [북한의 독특한 사회주의적 분위기], [선전적인 요소], [과거의 향수를 불러일으키는 분위기]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "silent_film_20s",
        "display_name_ko": "20년대 무성영화 (흑백, 높은 콘트라스트, 빈티지 그레인)",
        "display_name_vi": "Phim câm thập niên 20 (đen trắng, độ tương phản cao, hạt vintage)",
        "prompt_template": "[흑백 영상], [높은 콘트라스트], [빈티지 그레인], [과장된 몸짓과 표정], [자막 활용], [무성영화 특유의 찰리 채플린 스타일], [고전적인 코미디 분위기]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "camcorder_90s",
        "display_name_ko": "90년대 캠코더 (VHS 화질, 낮은 프레임)",
        "display_name_vi": "Máy quay thập niên 90 (chất lượng VHS, khung hình thấp)",
        "prompt_template": "[VHS 화질의 거칠고 노이즈가 많은 영상], [낮은 프레임], [90년대 캠코더 특유의 흐릿한 화질], [과거의 추억을 떠올리게 하는 분위기], [홈 비디오 스타일], [일상적인 모습]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "modern_drama",
        "display_name_ko": "현대 드라마 (자글자글한 화질, 자연스러운 색감)",
        "display_name_vi": "Phim truyền hình hiện đại (chất lượng grain, màu sắc tự nhiên)",
        "prompt_template": "[현대 드라마의 자글자글하고 거친 화질], [자연스러운 색감], [사실적인 묘사], [일상생활의 모습], [현대적인 도시 배경], [현실적인 분위기]",
        "gemini_instruction": ""
    },
    # 장르별 스타일
    {
        "preset_type": "script",
        "key_code": "mystery_thriller",
        "display_name_ko": "미스터리 스릴러 (저조도, 영사기 톤, 음영 그림자)",
        "display_name_vi": "Bí ẩn & Kinh dị (ánh sáng yếu, tông máy chiếu, bóng tối)",
        "prompt_template": "[저조도의 어둡고 미스터리한 분위기], [영사기 톤의 거친 화질], [음영 그림자를 활용한 긴장감 연출], [미스터리한 사건과 반전], [서스펜스적인 요소], [어둠 속의 비밀]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "horror_suspense",
        "display_name_ko": "공포-서스펜스 (어두운 조명, 음침 분위기)",
        "display_name_vi": "Kinh dị-Hồi hộp (ánh sáng tối, không khí u ám)",
        "prompt_template": "[어두운 조명], [음침하고 공포스러운 분위기], [공포 영화 특유의 깜짝 놀라는 연출], [무서운 괴물이나 귀신], [심리적인 공포], [소름 돋는 배경음악]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "melodrama",
        "display_name_ko": "멜로드라마 (부드러운 콘트라스트, 따뜻하고 화사함)",
        "display_name_vi": "Phim tình cảm (độ tương phản mềm, ấm áp và tươi sáng)",
        "prompt_template": "[부드러운 콘트라스트], [따뜻하고 화사한 색감], [로맨틱한 분위기], [사랑과 이별 이야기], [감동적인 연출], [아름다운 배경]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "crime_drama",
        "display_name_ko": "범죄 드라마 (차갑고 어두운 화질, 낮은 채도)",
        "display_name_vi": "Phim tội phạm (chất lượng lạnh và tối, độ bão hòa thấp)",
        "prompt_template": "[차갑고 어두운 화질], [낮은 채도], [범죄 현장의 황량하고 삭막한 분위기], [형사와 범죄자의 대결], [긴장감 넘치는 연출], [어두운 도시의 이면]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "cyberpunk_neon",
        "display_name_ko": "사이버펑크 네온 (네온 색상, 비, 미래적 분위기)",
        "display_name_vi": "Cyberpunk Neon (màu neon, mưa, không khí tương lai)",
        "prompt_template": "[네온 색상의 화려하고 현란한 빛], [비가 내리는 도시], [미래적이고 하이테크적인 분위기], [사이버네틱스 요소], [어두운 도시의 네온사인], [미래 사회의 이면]",
        "gemini_instruction": ""
    },
    # 캐릭터 웹툰 스타일
    {
        "preset_type": "script",
        "key_code": "k_comics",
        "display_name_ko": "K만화",
        "display_name_vi": "Truyện tranh K",
        "prompt_template": "[한국 웹툰 특유의 그림체], [다양한 캐릭터의 개성], [재미있는 스토리와 연출], [한국적인 요소], [웹툰 같은 만화 분위기]",
        "gemini_instruction": ""
    },
    # 일러스트 & 애니메이션
    {
        "preset_type": "script",
        "key_code": "watercolor_analog",
        "display_name_ko": "수채화 아날로그 (부드럽고 맑은 채색)",
        "display_name_vi": "Màu nước analog (tô màu mềm mại và trong sáng)",
        "prompt_template": "[수채화 특유의 부드럽고 맑은 채색], [아날로그적인 감성], [자연스러운 붓 터치], [꿈같은 분위기], [서정적인 일러스트]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "k_webtoon",
        "display_name_ko": "K웹툰",
        "display_name_vi": "Webtoon Hàn Quốc",
        "prompt_template": "[한국 웹툰의 세련되고 트렌디한 그림체], [인기 웹툰 같은 연출], [다양한 장르의 스토리], [화려한 색감], [한국 웹툰 고유의 매력]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "pencil_sketch",
        "display_name_ko": "연필 스케치 (흑백 정밀 데생)",
        "display_name_vi": "Phác thảo bút chì (vẽ đen trắng chính xác)",
        "prompt_template": "[연필 스케치의 거칠고 섬세한 선], [흑백 정밀 데생], [흑백 영상], [아날로그적인 감성], [예술적인 데생]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "joseon_2d_anime",
        "display_name_ko": "조선시대 2D 애니 (동양 판타지)",
        "display_name_vi": "Anime 2D thời Joseon (fantasy phương Đông)",
        "prompt_template": "[조선시대를 배경으로 한 2D 애니메이션], [동양 판타지 요소], [동양적인 색감과 그림체], [조선시대의 신비로운 이야기], [전통적인 아름다움]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "oriental_ink",
        "display_name_ko": "동양풍 수묵화 (수묵 담채화, 고전미)",
        "display_name_vi": "Tranh mực phương Đông (tranh mực nhạt, vẻ đẹp cổ điển)",
        "prompt_template": "[동양풍 수묵화의 은은하고 깊이 있는 색감], [수묵 담채화], [고전적인 아름다움], [수묵화 특유의 붓 터치], [서정적인 수묵화]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "neon_citypop",
        "display_name_ko": "네온사인 시티팝 (레트로 감성, 화려한 조명)",
        "display_name_vi": "Neon Citypop (cảm giác retro, ánh đèn rực rỡ)",
        "prompt_template": "[네온사인의 화려하고 현란한 빛], [레트로 감성의 시티팝 분위기], [80년대 일본의 도시 풍경], [화려한 조명], [팝아트 같은 분위기]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "buddhist_minimal",
        "display_name_ko": "불교 미니멀리즘 (단정하고 평온한 수묵)",
        "display_name_vi": "Tối giản Phật giáo (mực nước gọn gàng và bình yên)",
        "prompt_template": "[불교적인 미니멀리즘의 단정하고 평온한 분위기], [은은한 수묵화], [자연스러운 붓 터치], [명상적인 분위기], [불교적인 요소]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "renaissance_religious",
        "display_name_ko": "르네상스 종교화 (클래식 유화, 성스러운 빛 무늬)",
        "display_name_vi": "Tranh tôn giáo thời Phục Hưng (tranh sơn dầu cổ điển, ánh sáng thiêng liêng)",
        "prompt_template": "[르네상스 종교화의 클래식한 유화], [성스러운 빛 무늬], [고전적인 아름다움], [성서의 이야기], [화려하고 웅장한 분위기]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "cute_animal",
        "display_name_ko": "귀여운 동물 캐릭터 (캐주얼하고 친근함)",
        "display_name_vi": "Nhân vật động vật dễ thương (bình thường và thân thiện)",
        "prompt_template": "[귀여운 동물 캐릭터의 캐주얼하고 친근한 모습], [귀엽고 앙증맞은 외모], [친근하고 편안한 분위기], [동물 캐릭터 특유의 매력], [재미있는 연출]",
        "gemini_instruction": ""
    },
    {
        "preset_type": "script",
        "key_code": "nursery_rhyme",
        "display_name_ko": "동요 (Nursery Rhyme)",
        "display_name_vi": "Bài hát thiếu nhi (Nursery Rhyme)",
        "prompt_template": "[교육적이고 즐거운 어린이 동요], [쉽고 재미있는 가사와 멜로디], [어린이들이 좋아하는 귀여운 캐릭터와 영상], [신나는 분위기], [어린이 교육에 유익한 내용]",
        "gemini_instruction": ""
    },
]

def upsert_preset(preset):
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/style_presets"
    r = requests.post(url, headers=HEADERS, json=preset, verify=False)
    return r.status_code, r.text

print(f"총 {len(SCRIPT_STYLES)}개 대본 스타일 삽입 시작...\n")

success = 0
fail = 0
for style in SCRIPT_STYLES:
    code, text = upsert_preset(style)
    if code in (200, 201):
        print(f"  ✅ [{style['key_code']}] {style['display_name_ko']}")
        success += 1
    else:
        print(f"  ❌ [{style['key_code']}] FAILED: {code} - {text[:100]}")
        fail += 1

print(f"\n완료: 성공 {success}개 / 실패 {fail}개")
