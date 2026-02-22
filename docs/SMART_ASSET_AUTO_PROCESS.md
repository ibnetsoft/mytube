# 🎬 Smart Asset Auto-Processing 계획서

> **작성일**: 2026-02-20  
> **목적**: 영상/이미지 자산의 유형을 자동 감지하여 최적의 영상 효과를 적용하는 통합 파이프라인 구현  
> **담당 파일**: `services/video_service.py`, `services/gemini_service.py`

---

## 배경

사용자가 업로드하거나 AI가 생성하는 자산은 다양한 유형을 가진다:

| 자산 유형 | 예시 | 현재 문제 |
|-----------|------|-----------|
| 세로로 긴 영상 (9:32) | Seedance 생성 영상 | 중앙만 보이고 위/아래 잘림 |
| 4컷 만화 이미지 | 웹툰 패널 | 전체가 한 장면으로 처리됨 |
| 빠른 컷 편집 영상 | 유튜브 편집본 | 불필요한 zoom_in 추가됨 |
| 일반 가로 이미지 | AI 생성 1:1 or 16:9 | 정상 처리 |

---

## 구현 계획 (3단계)

---

### ✅ Level 1-A: 규칙 기반 자동 분석 (부분 구현 완료)

#### 구현된 항목

| 날짜 | 구현 내용 | 파일 | 함수 |
|------|-----------|------|------|
| 2026-02-20 | mp4 영상파일 + pan_down 효과 → Full-Travel Pan | `video_service.py` | `_preprocess_video_tall_pan()` |
| 2026-02-20 | **Gemini Vision 자산 유형 분류** | `gemini_service.py` | `classify_asset_type()` |
| 2026-02-20 | Autopilot 효과 미지정 시 → `auto_classify` 연동 | `autopilot_service.py` | 렌더 루프 |
| (기존) | 이미지 종횡비 > 2.0 → auto pan_down 전환 | `video_service.py` | `_create_cinematic_frame()` |
| (기존) | 세로 긴 이미지 컷 분할 | `video_service.py` | `_detect_and_split_panels()` |

#### `_preprocess_video_tall_pan()` 동작 원리

```
입력: 영상파일 (예: 1080x3840, 9:32 비율)
처리:
  ① ffprobe로 실제 해상도 측정
  ② width 기준 확대 → scaled_h 계산 (예: 3840px)
  ③ scroll_total = scaled_h - frame_h (이동 가능한 총 픽셀)
  ④ FFmpeg crop 필터:
     pan_down: y = 0 → scroll_total (Top→Bottom 전체 이동)
     pan_up:   y = scroll_total → 0  (Bottom→Top 전체 이동)
출력: 1080x1920 완성 영상 (Pan 효과 베이킹 완료)
```

---

### ❌ Level 1-B: 규칙 기반 자동 분석 (미구현)

#### 1. 영상 컷 수 자동 감지 → 컷별 처리

```python
# 목표 구현 위치: video_service.py > _detect_video_cut_type()
# 방법: FFprobe scene change detection
ffmpeg -i input.mp4 -filter:v "select='gt(scene,0.4)',showinfo" -f null -

# 감지 결과에 따른 효과:
# 컷 수 > 5, 각 컷 < 2초 → 효과 없음 (그대로 사용)
# 컷 수 <= 2, 컷 길이 > 3초 → zoom_in or pan
```

**구현 우선순위**: 높음  
**예상 작업**: 2~3시간

#### 2. 모션 벡터 분석 → 정적/동적 판단

```python
# 방법: 첫 프레임과 중간 프레임의 pixel diff 계산
# 영상 내 이미 움직임이 있으면 → 효과 없음
# 정적 영상 → zoom_in or pan_down 추가
```

**구현 우선순위**: 중간  
**예상 작업**: 1~2시간

#### 3. 이미지 격자 패턴 탐지 → 4분할 처리

```python
# 이미 _detect_and_split_panels()에서 부분 구현됨
# 추가 필요: 격자 구조(4컷/6컷) 명시적 탐지
# 방법: 수평선 패턴 + 색상 균일 구간 분석
```

**구현 우선순위**: 낮음 (현재 auto_split으로 어느정도 커버됨)

---

### ✅ Level 2: Gemini Vision 분류 (구현 완료 - 2026-02-20)

#### 구현 방법

```python
# 목표 구현 위치: services/gemini_service.py > classify_asset_type()
# 또는: video_service.py 내 인라인 호출

async def classify_asset_type(image_or_frame_path: str) -> dict:
    """
    이미지/영상 첫 프레임을 Gemini Vision으로 분류
    Returns: {
        "type": "tall_scene" | "comic_panel" | "fast_cut" | "normal",
        "effect": "pan_down" | "split_zoom" | "none" | "ken_burns",
        "confidence": 0.0 ~ 1.0
    }
    """
    prompt = """
    이 이미지의 유형을 아래 중 하나로 분류해줘:
    1. tall_scene: 세로로 긴 단일 장면 (스크롤해서 봐야 하는)
    2. comic_panel: 만화/웹툰 컷이 여러 개 모인 이미지
    3. fast_cut: 빠르게 편집된 영상 (이미 역동적임)
    4. normal: 일반 이미지
    
    JSON으로만 답해. 예시: {"type": "tall_scene", "confidence": 0.95}
    """
    # Gemini API 호출 (구현 필요)
```

#### 자동 효과 매핑

```python
EFFECT_MAP = {
    "tall_scene":   "pan_down",      # Full-travel pan
    "comic_panel":  "split_zoom",    # 각 컷별 순차 zoom-in  
    "fast_cut":     "none",          # 효과 없음 (영상 그대로)
    "normal":       "ken_burns",     # 기본 zoom_in/zoom_out
}
```

**비용**: Gemini API 1회 per 씬  
**구현 우선순위**: 높음 (Level 1-B보다 더 범용적)  
**예상 작업**: 3~4시간

---

### ❌ Level 3: 학습 기반 (미구현, 중장기)

```
사용자 피드백 수집:
  "이 씬 결과 좋았어" → DB에 (asset_type_hash, effect, rating) 저장
  
패턴 학습:
  → 유사한 자산에 동일 효과 자동 적용
  → 추후 통계 기반 기본값으로 evolve
```

**구현 우선순위**: 낮음 (현재 규모에서는 오버엔지니어링)

---

## 자동 처리 파이프라인 (완성 목표)

```
[영상/이미지 자산 입력]
         ↓
Level 1: 규칙 기반 분석 (빠름, 무료)
  ├── 종횡비 > 2.0? → pan_down full-travel  ✅ 구현완료
  ├── mp4 + pan_down 효과? → _preprocess_video_tall_pan()  ✅ 구현완료
  ├── 영상 내 컷 수 > 5? → 효과 없음  ❌ 미구현
  ├── 모션 벡터 동적? → 효과 없음  ❌ 미구현
  └── 격자 패턴? → 컷 분할 처리  ⚠️ 부분구현
         ↓ (위 규칙으로 판단 불가한 경우)
Level 2: Gemini Vision 분류 (비용 소요)
  ├── "tall_scene" → pan_down  ❌ 미구현
  ├── "comic_panel" → split_zoom  ❌ 미구현
  ├── "fast_cut" → none  ❌ 미구현
  └── "normal" → ken_burns  ❌ 미구현
         ↓
[최적 효과 자동 적용 완료]
```

---

## 다음 작업 우선순위

1. **[높음]** Level 2 Gemini Vision 분류 구현 - `classify_asset_type()` 함수 작성
2. **[높음]** Level 1-B: 영상 컷 수 감지 (FFprobe scene change)
3. **[중간]** Level 1-B: 모션 벡터 기반 정적/동적 판단
4. **[낮음]** Level 3: 사용자 피드백 수집 DB 구조 설계

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `services/video_service.py` | 핵심 영상 처리 로직 |
| `services/gemini_service.py` | Gemini API 연동 (Level 2 추가 예정) |
| `services/autopilot_service.py` | 효과 자동 선택 로직 (1450줄 참고) |
| `app/routers/video.py` | 렌더링 API 엔드포인트 |
