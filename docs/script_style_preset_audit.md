# 대본 스타일 프리셋(script_style_presets) 전수 감사

기준 시점: 이번 정비 작업 직전 (43개 키, `data/*.db`의 `script_style_presets` 테이블).
전체 원본 덤프(정비 전): `scratchpad/style_qa/script_style_dump.json` (세션 로컬, 참고용, 저장소에는 커밋하지 않음).

## 분류 기준

- **A. 정상적인 대본 작성 스타일** — 서술자 톤/문장 리듬/어휘/전개 방식 등 실제 "글쓰기"에 대한 지침.
- **B. 이미지·영상 연출 스타일** — 색감·화질·조명·작화 등 순수 시각 연출 묘사. 글쓰기 지침 요소가 사실상 없음.
- **C. 대본과 시각 스타일이 혼합** — 일부 글쓰기 신호(분위기/톤/서사 키워드)와 시각 묘사가 섞여 있음.
- **D. 중복 별칭** — 다른 키와 내용이 완전히 동일(또는 사실상 동일)한 레거시 키.
- **E. 빈 값 또는 사실상 무효** — 이번 감사에서는 해당 키 없음 (43개 전부 prompt_value가 채워져 있었음).
- **F. 용도를 판단하기 어려움** — 다른 키와 개념이 겹치거나 목적이 불분명해 별도 검토가 필요.

## 43개 키 전수 분류

| key | 표시명 | 프롬프트 요약(정비 전) | 분류 | 대본 스타일 사용 가능? | canonical key | 별칭? | 수정 필요? |
|---|---|---|---|---|---|---|---|
| default | 기본 설정 | "자연스럽고 선명한 색감, 깨끗하고 투명한 화질..." (순수 영상미) | B | 아니오(정비 전) | default | 아니오 | **완료(1차)** |
| news | 뉴스 보도 | "뉴스 앵커 톤의 차분한 목소리, 정확한 발음, 또렷한 딕션..." | C | 부분적(정비 전) | news | 아니오 | **완료(1차)** |
| story | 옛날 이야기 | "할머니가 들려주시는 듯한 목소리, 구수한 입담..." | C | 부분적(정비 전) | story | 아니오 | **완료(1차)** |
| old_story | 옛날 이야기 | story와 완전 동일 | D | - | story | **예** | 불필요(별칭) |
| senior_story | 시니어 사연 | "차분하고 깊이 있는 목소리, 풍부한 경험담..." | C | 부분적(정비 전) | senior_story | 아니오 | **완료(1차)** |
| script_master | (기본스타일과 별개) | 4단계 딥다이브 대본 빌드업 풀 프로세스 (3,300자) | A | 예 | script_master | 아니오 | 불필요(이미 양호) |
| basic | 기본스타일 | script_master와 거의 동일한 내용(초기 버전으로 추정) | D(사실상) | - | script_master | 사실상 예 | 불필요(별칭 취급 권장, 통합 미실시) |
| bgm | 배경음악 중심 | "배경음악에 맞춰 변하는 영상 연출, 리듬을 시각적으로 표현..." | B | 아니오 | bgm | 아니오 | 미실시(범위 밖) |
| bgm_focus | 배경음악 중심 | bgm과 완전 동일 | D | - | bgm | **예** | 불필요(별칭) |
| classic_50s | 50년대 클래식 영화 | "테크니컬러의 풍부한 색감, 부드러운 조명..." | B | 아니오 | classic_50s | 아니오 | 미실시(범위 밖) |
| joseon_sageuk | 조선시대 사극 | "조선시대 전통 건축과 의복, 자연광, 한옥과 궁궐 배경..." | B | 아니오(정비 전) | joseon_sageuk | 아니오 | **완료(1차)** |
| joseon_drama | 조선시대 사극 | joseon_sageuk과 완전 동일 | D | - | joseon_sageuk | **예** | 불필요(별칭) |
| north_korean_drama | 북한 드라마 | "빈티지 영화의 거친 화질, 강렬한 색감, 사회주의적 분위기..." | B | 아니오 | north_korean_drama | 아니오 | 미실시(범위 밖) |
| north_korea_drama | 북한 드라마 | north_korean_drama와 완전 동일 | D | - | north_korean_drama | **예** | 불필요(별칭) |
| silent_20s | 20년대 무성영화 | "흑백 영상, 높은 콘트라스트, 찰리 채플린 스타일..." | B | 아니오 | silent_20s | 아니오 | 미실시(범위 밖) |
| silent_film_20s | 20년대 무성영화 | silent_20s와 완전 동일 | D | - | silent_20s | **예** | 불필요(별칭) |
| camcorder_90s | 90년대 캠코더 | "VHS 화질, 낮은 프레임, 홈비디오 스타일..." | B | 아니오 | camcorder_90s | 아니오 | 미실시(범위 밖) |
| modern_drama | 현대 드라마 | "자글자글한 화질, 자연스러운 색감, 일상생활 모습..." | B | 아니오 | modern_drama | 아니오 | 미실시(범위 밖) |
| mystery_thriller | 미스터리 스릴러 | "저조도, 영사기 톤, 서스펜스적 요소, 어둠 속 비밀..." | C | 부분적 | mystery_thriller | 아니오 | 미실시(범위 밖, horror_suspense와 개념 인접 - F 후보) |
| horror_suspense | 공포-서스펜스 | "어두운 조명, 음침한 분위기, 심리적 공포..." | C | 부분적(정비 전) | horror_suspense | 아니오 | **완료(1차)** |
| melodrama | 멜로드라마 | "부드러운 콘트라스트, 로맨틱한 분위기, 사랑과 이별 이야기..." | C | 부분적 | melodrama | 아니오 | 미실시(범위 밖) |
| crime_drama | 범죄 드라마 | "차갑고 어두운 화질, 형사와 범죄자의 대결..." | C | 부분적 | crime_drama | 아니오 | 미실시(범위 밖) |
| cyberpunk_neon | 사이버펑크 네온 | "네온 색상, 사이버네틱스 요소, 미래 사회의 이면..." | B/C | 부분적 | cyberpunk_neon | 아니오 | 미실시(범위 밖) |
| watercolor_analog | 수채화 아날로그 | "수채화 특유의 채색, 아날로그적 감성, 서정적 일러스트..." | B | 아니오 | watercolor_analog | 아니오 | 미실시(범위 밖) |
| digital_webtoon | (표시명 없음) | "선명한 라인, 화려한 색감, 간결하고 빠른 전개" | C | 부분적 | digital_webtoon | 아니오 | 미실시(k_webtoon과 개념 중복 - F 후보) |
| graphite_sketch | 연필 스케치 | "연필 스케치의 거친 선, 흑백 정밀 데생..." | B | 아니오 | graphite_sketch | 아니오 | 미실시(범위 밖) |
| pencil_sketch | 연필 스케치 | graphite_sketch와 완전 동일 | D | - | graphite_sketch | **예** | 불필요(별칭) |
| joseon_2d_anime | 조선시대 2D 애니 | "조선시대 배경 2D 애니메이션, 동양 판타지 요소..." | B | 아니오 | joseon_2d_anime | 아니오 | 미실시(joseon_sageuk과 개념 인접 - F 후보) |
| oriental_ink | 동양풍 수묵화 | "수묵 담채화, 고전적인 아름다움, 붓 터치..." | B | 아니오 | oriental_ink | 아니오 | 미실시(범위 밖) |
| neonsign_citypop | 네온사인 시티팝 | "네온사인의 화려한 빛, 레트로 시티팝 분위기..." | B | 아니오 | neonsign_citypop | 아니오 | 미실시(범위 밖) |
| neon_citypop | 네온사인 시티팝 | neonsign_citypop과 완전 동일 | D | - | neonsign_citypop | **예** | 불필요(별칭) |
| buddhist_minimal | 불교 미니멀리즘 | "단정하고 평온한 분위기, 은은한 수묵화, 명상적 분위기..." | B | 아니오 | buddhist_minimal | 아니오 | 미실시(범위 밖) |
| renaissance_sacred | 르네상스 종교화 | "클래식한 유화, 성스러운 빛 무늬..." | B | 아니오 | renaissance_sacred | 아니오 | 미실시(범위 밖) |
| renaissance_religious | 르네상스 종교화 | renaissance_sacred와 완전 동일 | D | - | renaissance_sacred | **예** | 불필요(별칭) |
| cute_animal_char | 귀여운 동물 캐릭터 | "캐주얼하고 친근한 모습, 귀엽고 앙증맞은 외모..." | B | 아니오 | cute_animal_char | 아니오 | 미실시(범위 밖) |
| cute_animal | 귀여운 동물 캐릭터 | cute_animal_char와 완전 동일 | D | - | cute_animal_char | **예** | 불필요(별칭) |
| k_manhwa | K만화 | "한국 웹툰 특유의 그림체, 재미있는 스토리와 연출..." | B/C | 부분적 | k_manhwa | 아니오 | 미실시(범위 밖, k_webtoon과 개념 인접 - F 후보) |
| k_comics | K만화 | k_manhwa와 완전 동일 | D | - | k_manhwa | **예** | 불필요(별칭) |
| k_webtoon | K웹툰 | "세련되고 트렌디한 그림체, 다양한 장르의 스토리..." | C | 부분적(정비 전) | k_webtoon | 아니오 | **완료(1차)** |
| wimpy_kid | (표시명 없음) | 영문 풀 라이팅 스타일 프롬프트(스토익/미니멀 자기계발 숏폼) | A | 예 | wimpy_kid | 아니오 | 불필요(이미 양호) |
| sports_analysis | (표시명 없음) | 영문 1줄 요약("Analytical, energetic, data-driven...") | A(축약) | 예(짧음) | sports_analysis | 아니오 | **완료(1차, 보강)** |
| nursery_rhyme | 동요 | "교육적이고 즐거운 어린이 동요, 쉽고 재미있는 가사와 멜로디..." | C | 부분적 | nursery_rhyme | 아니오 | 미실시(범위 밖) |
| yoga_kids | (표시명 없음) | 타겟/테마/제목형식/스크립트 규칙을 갖춘 상세 지침(영문) | A | 예 | yoga_kids | 아니오 | 불필요(이미 양호) |
| documentary | *(신규 생성)* | 없음(43개 목록에 없었음 - 이번에 신규 추가) | - | - | documentary | 아니오 | **완료(1차, 신규 생성)** |

## 요약

- 정비 전 A(정상) 등급: `script_master`, `wimpy_kid`, `yoga_kids`, `sports_analysis`(축약) — 4개뿐.
- B(순수 영상 연출) 등급: 약 20개. 대부분 이번 범위 밖(별도 후속 작업 권장).
- C(혼합) 등급: 약 10개.
- D(중복 별칭): 10쌍(과제에서 지정한 그대로 확인됨) + `basic`≈`script_master`(사실상 중복이나 alias map에는 미포함, 아래 참고).
- 이번에 1차로 정비(글쓰기 지침으로 전면 교체 또는 신규 생성): `default`, `news`, `story`, `senior_story`, `joseon_sageuk`, `horror_suspense`, `k_webtoon`, `sports_analysis`(보강), `documentary`(신규) — **9개 수정 + 1개 신규 = 10개**.
- 남은 미정비 스타일: **43 + 1(documentary) - 10(1차 완료) = 34개** (D 별칭 10개 포함). 실질적으로 "글쓰기 지침 전면 교체가 필요한 B/C 등급"은 약 24개 남음.

## F 등급(개념 중복/판단 보류) 후보 — 후속 검토 필요

- `mystery_thriller` vs `horror_suspense`: 장르가 인접해 있어 둘 다 남겨둘지, 하나로 통합할지 상품 기획 판단이 필요.
- `digital_webtoon` vs `k_webtoon` vs `k_manhwa`(`k_comics`): "웹툰/만화" 계열 키가 3종으로 분산되어 있어 정리가 필요.
- `joseon_2d_anime` vs `joseon_sageuk`(`joseon_drama`): 둘 다 "조선시대"이나 하나는 애니메이션, 하나는 실사 사극 — 유지하되 표시명에 매체 구분을 명확히 하는 것을 권장.
- `basic` vs `script_master`: 내용이 사실상 동일(초기 버전/최신 버전 관계로 추정). alias map에는 포함하지 않았음(과제에서 지정한 10쌍 외 임의 추가 자제) — 별도 논의 후 `basic`을 alias로 편입할지 결정 필요.

**주의**: 이번 감사에서 D(별칭) 확인 이상의 정리(중복 키 삭제, F 등급 통합)는 수행하지 않았다. 임의 삭제·대량 변경 금지 지침에 따름.
